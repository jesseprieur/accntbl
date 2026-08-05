"""Full-snapshot export/import for point-in-time backups.

See specs.md § "Backup / import-export" for the full design. Export walks
every backed-up table generically via `__table__.columns` so new columns
are picked up automatically; import mirrors that generically too, then
re-runs the recurring-occurrence generator to regenerate `attached`
transaction rows (which are deliberately not exported).
"""
import enum
import os
from datetime import date, timedelta
from decimal import Decimal

from alembic.config import Config
from alembic.script import ScriptDirectory
from flask import current_app

from app.extensions import db
from app.models import (
    CheckingAccount,
    CreditCard,
    CreditDueOverride,
    OccurrenceStatus,
    RecurringSeries,
    Transaction,
)
from app.services.recurring import generate_occurrences

_MATERIALIZE_FUTURE_DAYS = 365


def get_alembic_head():
    """Return the current Alembic head revision id for this app's migrations."""
    migrations_dir = os.path.join(current_app.root_path, "..", "migrations")
    config = Config()
    config.set_main_option("script_location", migrations_dir)
    return ScriptDirectory.from_config(config).get_current_head()


def _serialize_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    return value


def _serialize_row(instance):
    return {
        column.name: _serialize_value(getattr(instance, column.name))
        for column in instance.__table__.columns
    }


def _deserialize_row(model, row):
    kwargs = {}
    for column in model.__table__.columns:
        value = row.get(column.name)
        if value is not None:
            if isinstance(column.type, db.Date):
                value = date.fromisoformat(value)
            elif isinstance(column.type, db.Numeric):
                value = Decimal(value)
            elif isinstance(column.type, db.Enum):
                value = column.type.enum_class(value)
        kwargs[column.name] = value
    return model(**kwargs)


def build_snapshot():
    """Return the full backup snapshot as a JSON-serializable dict."""
    exportable_transactions = Transaction.query.filter(
        db.or_(
            Transaction.recurring_series_id.is_(None),
            Transaction.occurrence_status.in_(
                [OccurrenceStatus.detached, OccurrenceStatus.skipped]
            ),
        )
    ).order_by(Transaction.id)

    return {
        "schema_version": get_alembic_head(),
        "checking_accounts": [
            _serialize_row(row)
            for row in CheckingAccount.query.order_by(CheckingAccount.id)
        ],
        "credit_cards": [
            _serialize_row(row) for row in CreditCard.query.order_by(CreditCard.id)
        ],
        "credit_due_overrides": [
            _serialize_row(row)
            for row in CreditDueOverride.query.order_by(CreditDueOverride.id)
        ],
        "recurring_series": [
            _serialize_row(row)
            for row in RecurringSeries.query.order_by(RecurringSeries.id)
        ],
        "transactions": [_serialize_row(row) for row in exportable_transactions],
    }


def restore_snapshot(data):
    """Replace all current data with the given backup snapshot.

    Raises ValueError if the backup's schema_version doesn't match the
    current Alembic head. Rolls back entirely on any failure so the DB is
    never left partially restored.
    """
    current_head = get_alembic_head()
    backup_version = data.get("schema_version")
    if backup_version != current_head:
        raise ValueError(
            f"Backup schema_version ({backup_version!r}) does not match "
            f"the current schema ({current_head!r})."
        )

    try:
        Transaction.query.delete(synchronize_session=False)
        RecurringSeries.query.delete(synchronize_session=False)
        CreditDueOverride.query.delete(synchronize_session=False)
        CreditCard.query.delete(synchronize_session=False)
        CheckingAccount.query.delete(synchronize_session=False)

        for row in data.get("checking_accounts", []):
            db.session.add(_deserialize_row(CheckingAccount, row))
        for row in data.get("credit_cards", []):
            db.session.add(_deserialize_row(CreditCard, row))
        for row in data.get("credit_due_overrides", []):
            db.session.add(_deserialize_row(CreditDueOverride, row))

        series_list = [
            _deserialize_row(RecurringSeries, row)
            for row in data.get("recurring_series", [])
        ]
        db.session.add_all(series_list)
        for row in data.get("transactions", []):
            db.session.add(_deserialize_row(Transaction, row))

        db.session.flush()

        horizon = date.today() + timedelta(days=_MATERIALIZE_FUTURE_DAYS)
        for series in series_list:
            range_end = (
                min(series.end_date, horizon) if series.end_date is not None else horizon
            )
            for occurrence_date in generate_occurrences(
                series, series.start_date, range_end
            ):
                db.session.add(
                    Transaction(
                        name=series.name,
                        kind=series.kind,
                        amount=series.amount,
                        date=occurrence_date,
                        notes=series.notes,
                        recurring_series_id=series.id,
                        occurrence_status=OccurrenceStatus.attached,
                        credit_card_id=series.credit_card_id,
                    )
                )

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

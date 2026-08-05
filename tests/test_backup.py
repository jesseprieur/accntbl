import datetime as dt
from decimal import Decimal

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import (
    CadenceType,
    CheckingAccount,
    CreditCard,
    CreditDueOverride,
    Kind,
    OccurrenceStatus,
    RecurringSeries,
    Transaction,
    User,
)
from app.services.backup import build_snapshot, get_alembic_head, restore_snapshot
from app.services.recurring import generate_occurrences


def _seed_sample_data():
    checking = CheckingAccount(
        name="Primary Checking",
        starting_balance=Decimal("1000.00"),
        as_of_date=dt.date(2026, 7, 1),
    )
    db.session.add(checking)

    card = CreditCard(
        name="Visa",
        is_default=True,
        statement_close_day=15,
        payment_due_offset_days=20,
        starting_balance=Decimal("-250.00"),
        starting_balance_due_date=dt.date(2026, 8, 4),
    )
    db.session.add(card)
    db.session.flush()

    override = CreditDueOverride(
        credit_card_id=card.id,
        due_date=dt.date(2026, 8, 4),
        amount=Decimal("-300.00"),
        notes="estimated ahead",
    )
    db.session.add(override)

    series = RecurringSeries(
        name="Rent",
        kind=Kind.cash,
        amount=Decimal("-400.00"),
        cadence_type=CadenceType.monthly,
        start_date=dt.date(2026, 7, 1),
        end_date=None,
    )
    db.session.add(series)
    db.session.flush()

    horizon = dt.date.today() + dt.timedelta(days=365)
    for occurrence_date in generate_occurrences(series, series.start_date, horizon):
        db.session.add(
            Transaction(
                name=series.name,
                kind=series.kind,
                amount=series.amount,
                date=occurrence_date,
                recurring_series_id=series.id,
                occurrence_status=OccurrenceStatus.attached,
            )
        )

    detached = Transaction(
        name="Rent",
        kind=Kind.cash,
        amount=Decimal("-450.00"),
        date=dt.date(2026, 8, 1),
        recurring_series_id=series.id,
        occurrence_status=OccurrenceStatus.detached,
    )
    db.session.add(detached)

    skipped = Transaction(
        name="Rent",
        kind=Kind.cash,
        amount=Decimal("-400.00"),
        date=dt.date(2026, 9, 1),
        recurring_series_id=series.id,
        occurrence_status=OccurrenceStatus.skipped,
    )
    db.session.add(skipped)

    one_off = Transaction(
        name="Gift",
        kind=Kind.cash,
        amount=Decimal("50.00"),
        date=dt.date(2026, 7, 12),
    )
    db.session.add(one_off)

    db.session.commit()
    return series.id


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        db.session.add(
            User(username="anita", password_hash=generate_password_hash("secret123"))
        )
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    client = app.test_client()
    client.post("/login", data={"username": "anita", "password": "secret123"})
    return client


def test_download_backup_requires_login(app):
    anon_client = app.test_client()
    response = anon_client.get("/settings/backup")
    assert response.status_code == 302


def test_export_produces_valid_complete_snapshot(app):
    with app.app_context():
        _seed_sample_data()

        snapshot = build_snapshot()

        assert snapshot["schema_version"] == get_alembic_head()
        assert len(snapshot["checking_accounts"]) == 1
        assert len(snapshot["credit_cards"]) == 1
        assert len(snapshot["credit_due_overrides"]) == 1
        assert len(snapshot["recurring_series"]) == 1

        exported_txn_statuses = {
            (row["name"], row.get("occurrence_status")) for row in snapshot["transactions"]
        }
        assert ("Rent", "detached") in exported_txn_statuses
        assert ("Rent", "skipped") in exported_txn_statuses
        assert ("Gift", None) in exported_txn_statuses
        # attached series occurrences are re-derived on import, not exported
        assert not any(
            row["occurrence_status"] == "attached" for row in snapshot["transactions"]
        )


def test_import_round_trip_matches_original_data(app):
    with app.app_context():
        _seed_sample_data()
        snapshot = build_snapshot()

        original_attached_dates = sorted(
            t.date
            for t in Transaction.query.filter_by(occurrence_status=OccurrenceStatus.attached)
        )

        Transaction.query.delete()
        RecurringSeries.query.delete()
        CreditDueOverride.query.delete()
        CreditCard.query.delete()
        CheckingAccount.query.delete()
        db.session.commit()

        restore_snapshot(snapshot)

        assert CheckingAccount.query.count() == 1
        account = CheckingAccount.query.one()
        assert account.name == "Primary Checking"
        assert account.starting_balance == Decimal("1000.00")

        card = CreditCard.query.one()
        assert card.name == "Visa"
        assert card.is_default is True

        override = CreditDueOverride.query.one()
        assert override.amount == Decimal("-300.00")
        assert override.credit_card_id == card.id

        series = RecurringSeries.query.one()
        assert series.name == "Rent"

        detached = Transaction.query.filter_by(occurrence_status=OccurrenceStatus.detached).one()
        assert detached.date.isoformat() == "2026-08-01"

        skipped = Transaction.query.filter_by(occurrence_status=OccurrenceStatus.skipped).one()
        assert skipped.date.isoformat() == "2026-09-01"

        one_off = Transaction.query.filter_by(name="Gift").one()
        assert one_off.recurring_series_id is None

        restored_attached_dates = sorted(
            t.date
            for t in Transaction.query.filter_by(occurrence_status=OccurrenceStatus.attached)
        )
        assert restored_attached_dates == original_attached_dates


def test_import_rejects_schema_version_mismatch_and_leaves_db_unchanged(app):
    with app.app_context():
        _seed_sample_data()
        snapshot = build_snapshot()
        snapshot["schema_version"] = "not-a-real-revision"

        with pytest.raises(ValueError):
            restore_snapshot(snapshot)

        assert CheckingAccount.query.count() == 1
        assert Transaction.query.count() > 0


def test_import_failure_rolls_back_leaving_db_unchanged(app):
    with app.app_context():
        _seed_sample_data()
        snapshot = build_snapshot()
        # Corrupt a row so deserialization blows up mid-import.
        snapshot["checking_accounts"][0]["as_of_date"] = "not-a-date"

        with pytest.raises(ValueError):
            restore_snapshot(snapshot)

        assert CheckingAccount.query.count() == 1
        assert CheckingAccount.query.one().name == "Primary Checking"


def test_restore_backup_endpoint_round_trip(client, app):
    with app.app_context():
        _seed_sample_data()

    download_response = client.get("/settings/backup")
    assert download_response.status_code == 200
    assert download_response.mimetype == "application/json"

    from io import BytesIO

    upload_response = client.post(
        "/settings/backup/restore",
        data={"backup_file": (BytesIO(download_response.data), "backup.json")},
        content_type="multipart/form-data",
    )
    assert upload_response.status_code == 302

    with app.app_context():
        assert CheckingAccount.query.count() == 1

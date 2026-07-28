"""Paginated transaction window endpoint.

Returns a date-bounded slice of the ledger (real `transactions` rows merged
with virtual credit-card payment-due rows), with running totals computed
from the full transaction history up to the window's end so that a window
that doesn't start at the beginning of time still reports a correct running
total. See specs.md's "Running total calculation" and "Main table view".
"""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request

from app.auth import login_required
from app.extensions import db
from app.models import (
    CadenceType,
    CheckingAccount,
    CreditCard,
    CreditDueOverride,
    CustomIntervalUnit,
    Kind,
    OccurrenceStatus,
    RecurringSeries,
    Transaction,
)
from app.services.recurring import generate_occurrences
from app.services.running_total import compute_running_total

transactions_bp = Blueprint("transactions", __name__, url_prefix="/transactions")

_DEFAULT_PAST_DAYS = 30
_DEFAULT_FUTURE_DAYS = 90
_MATERIALIZE_FUTURE_DAYS = 365


def _parse_date_param(value, field_label):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"{field_label} must be a valid YYYY-MM-DD date.")


def _parse_decimal_field(value, field_label):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{field_label} must be a number.")


def _parse_enum_field(enum_cls, value, field_label):
    try:
        return enum_cls(value)
    except ValueError:
        allowed = ", ".join(member.value for member in enum_cls)
        raise ValueError(f"{field_label} must be one of: {allowed}.")


def _resolve_credit_card_id(kind, requested_id, existing_id):
    """Resolve `credit_card_id` for a transaction/series being created or edited.

    Cash entities never carry a card. Credit entities keep an explicitly
    requested card (validated to exist), otherwise keep their current card,
    otherwise fall back to the default card.
    """
    if kind == Kind.cash:
        return None

    if requested_id is not None:
        try:
            card_id = int(requested_id)
        except (TypeError, ValueError):
            raise ValueError("Credit card is invalid.")
        if not CreditCard.query.get(card_id):
            raise ValueError("Credit card not found.")
        return card_id

    if existing_id is not None:
        return existing_id

    default_card = CreditCard.query.filter_by(is_default=True).first()
    if default_card is None:
        raise ValueError("A credit card is required; add one in Settings first.")
    return default_card.id


@transactions_bp.route("/window", methods=["GET"])
@login_required
def window():
    today = date.today()

    try:
        start = (
            _parse_date_param(request.args["start"], "start")
            if "start" in request.args
            else today - timedelta(days=_DEFAULT_PAST_DAYS)
        )
        end = (
            _parse_date_param(request.args["end"], "end")
            if "end" in request.args
            else today + timedelta(days=_DEFAULT_FUTURE_DAYS)
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if start > end:
        return jsonify({"error": "start must not be after end."}), 400

    include_skipped = request.args.get("include_skipped") == "1"

    history = Transaction.query.filter(Transaction.date <= end).order_by(
        Transaction.date
    ).all()

    checking_accounts = CheckingAccount.query.all()
    credit_cards = CreditCard.query.all()
    credit_due_overrides = CreditDueOverride.query.all()

    full_range_start = min((t.date for t in history), default=start)
    full_range_start = min(full_range_start, start)

    ledger = compute_running_total(
        checking_accounts,
        history,
        credit_cards,
        full_range_start,
        end,
        credit_due_overrides=credit_due_overrides,
    )

    rows = [
        {
            "id": row.transaction.id if row.transaction is not None else None,
            "name": row.name,
            "date": row.date.isoformat(),
            "cash_amount": str(row.cash_amount),
            "credit_amount": (
                str(row.transaction.amount)
                if row.transaction is not None and row.transaction.kind == Kind.credit
                else None
            ),
            "notes": row.transaction.notes if row.transaction is not None else None,
            "credit_card_id": (
                row.transaction.credit_card_id
                if row.transaction is not None
                else row.credit_card_id
            ),
            "recurring_series_id": (
                row.transaction.recurring_series_id
                if row.transaction is not None
                else None
            ),
            "occurrence_status": (
                row.transaction.occurrence_status.value
                if row.transaction is not None and row.transaction.occurrence_status
                else None
            ),
            "running_total": str(row.running_total),
            "is_negative": row.is_negative,
            "is_virtual": row.transaction is None,
            "is_override": row.is_override,
            "is_month_end": row.is_month_end,
            "month_over_month_change": (
                str(row.month_over_month_change)
                if row.month_over_month_change is not None
                else None
            ),
        }
        for row in ledger
        if start <= row.date <= end
    ]

    if include_skipped:
        skipped_rows = [
            {
                "id": t.id,
                "name": t.name,
                "date": t.date.isoformat(),
                "cash_amount": str(t.amount) if t.kind == Kind.cash else "0",
                "credit_amount": str(t.amount) if t.kind == Kind.credit else None,
                "notes": t.notes,
                "credit_card_id": t.credit_card_id,
                "recurring_series_id": t.recurring_series_id,
                "occurrence_status": t.occurrence_status.value,
                "running_total": None,
                "is_negative": False,
                "is_virtual": False,
                "is_override": False,
                "is_month_end": False,
                "month_over_month_change": None,
            }
            for t in history
            if t.occurrence_status == OccurrenceStatus.skipped and start <= t.date <= end
        ]
        rows = sorted(rows + skipped_rows, key=lambda r: r["date"])

    return jsonify({"start": start.isoformat(), "end": end.isoformat(), "rows": rows})


@transactions_bp.route("", methods=["POST"])
@login_required
def create():
    payload = request.get_json(silent=True) or {}

    try:
        name = (payload.get("name") or "").strip()
        if not name:
            raise ValueError("Name is required.")

        if "date" not in payload or not payload["date"]:
            raise ValueError("Date is required.")
        txn_date = _parse_date_param(payload["date"], "Date")

        kind = _parse_enum_field(Kind, payload.get("kind"), "Kind")

        amount = _parse_decimal_field(payload.get("amount"), "Amount")
        if amount is None:
            raise ValueError("Amount is required.")

        notes = payload.get("notes") or None

        credit_card_id = _resolve_credit_card_id(
            kind, payload.get("credit_card_id"), None
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    transaction = Transaction(
        name=name,
        kind=kind,
        amount=amount,
        date=txn_date,
        notes=notes,
        credit_card_id=credit_card_id,
    )
    db.session.add(transaction)
    db.session.commit()

    return jsonify(
        {
            "id": transaction.id,
            "name": transaction.name,
            "date": transaction.date.isoformat(),
            "kind": transaction.kind.value,
            "amount": str(transaction.amount),
            "notes": transaction.notes,
            "credit_card_id": transaction.credit_card_id,
            "recurring_series_id": transaction.recurring_series_id,
            "occurrence_status": None,
        }
    ), 201


@transactions_bp.route("/series", methods=["POST"])
@login_required
def create_series():
    payload = request.get_json(silent=True) or {}

    try:
        name = (payload.get("name") or "").strip()
        if not name:
            raise ValueError("Name is required.")

        kind = _parse_enum_field(Kind, payload.get("kind"), "Kind")

        amount = _parse_decimal_field(payload.get("amount"), "Amount")
        if amount is None:
            raise ValueError("Amount is required.")

        cadence_type = _parse_enum_field(
            CadenceType, payload.get("cadence_type"), "Cadence"
        )

        custom_interval_value = None
        custom_interval_unit = None
        if cadence_type == CadenceType.custom:
            custom_interval_value = payload.get("custom_interval_value")
            try:
                custom_interval_value = int(custom_interval_value)
                if custom_interval_value <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                raise ValueError(
                    "Custom interval value is required and must be a positive integer."
                )
            custom_interval_unit = _parse_enum_field(
                CustomIntervalUnit,
                payload.get("custom_interval_unit"),
                "Custom interval unit",
            )

        if "start_date" not in payload or not payload["start_date"]:
            raise ValueError("Start date is required.")
        start_date = _parse_date_param(payload["start_date"], "Start date")

        end_date = None
        if payload.get("end_date"):
            end_date = _parse_date_param(payload["end_date"], "End date")
            if end_date < start_date:
                raise ValueError("End date must not be before start date.")

        notes = payload.get("notes") or None

        credit_card_id = _resolve_credit_card_id(
            kind, payload.get("credit_card_id"), None
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    series = RecurringSeries(
        name=name,
        kind=kind,
        amount=amount,
        cadence_type=cadence_type,
        custom_interval_value=custom_interval_value,
        custom_interval_unit=custom_interval_unit,
        start_date=start_date,
        end_date=end_date,
        notes=notes,
        credit_card_id=credit_card_id,
    )
    db.session.add(series)
    db.session.flush()

    horizon = date.today() + timedelta(days=_MATERIALIZE_FUTURE_DAYS)
    range_end = min(end_date, horizon) if end_date is not None else horizon
    occurrence_dates = generate_occurrences(series, start_date, range_end)

    for occurrence_date in occurrence_dates:
        db.session.add(
            Transaction(
                name=series.name,
                kind=kind,
                amount=amount,
                date=occurrence_date,
                notes=notes,
                recurring_series_id=series.id,
                occurrence_status=OccurrenceStatus.attached,
                credit_card_id=credit_card_id,
            )
        )

    db.session.commit()

    return jsonify(
        {
            "id": series.id,
            "name": series.name,
            "kind": series.kind.value,
            "amount": str(series.amount),
            "cadence_type": series.cadence_type.value,
            "custom_interval_value": series.custom_interval_value,
            "custom_interval_unit": (
                series.custom_interval_unit.value
                if series.custom_interval_unit
                else None
            ),
            "start_date": series.start_date.isoformat(),
            "end_date": series.end_date.isoformat() if series.end_date else None,
            "notes": series.notes,
            "credit_card_id": series.credit_card_id,
            "occurrences_created": len(occurrence_dates),
        }
    ), 201


@transactions_bp.route("/series", methods=["GET"])
@login_required
def list_series():
    series = RecurringSeries.query.order_by(RecurringSeries.name).all()
    return jsonify(
        {
            "series": [
                {
                    "id": s.id,
                    "name": s.name,
                    "kind": s.kind.value,
                    "amount": str(s.amount),
                    "cadence_type": s.cadence_type.value,
                    "custom_interval_value": s.custom_interval_value,
                    "custom_interval_unit": (
                        s.custom_interval_unit.value if s.custom_interval_unit else None
                    ),
                    "start_date": s.start_date.isoformat(),
                    "end_date": s.end_date.isoformat() if s.end_date else None,
                    "notes": s.notes,
                    "credit_card_id": s.credit_card_id,
                }
                for s in series
            ]
        }
    )


@transactions_bp.route("/series/<int:series_id>", methods=["GET"])
@login_required
def get_series(series_id):
    series = RecurringSeries.query.get_or_404(series_id)

    return jsonify(
        {
            "id": series.id,
            "name": series.name,
            "kind": series.kind.value,
            "amount": str(series.amount),
            "cadence_type": series.cadence_type.value,
            "custom_interval_value": series.custom_interval_value,
            "custom_interval_unit": (
                series.custom_interval_unit.value
                if series.custom_interval_unit
                else None
            ),
            "start_date": series.start_date.isoformat(),
            "end_date": series.end_date.isoformat() if series.end_date else None,
            "notes": series.notes,
            "credit_card_id": series.credit_card_id,
        }
    )


@transactions_bp.route("/series/<int:series_id>", methods=["PATCH"])
@login_required
def update_series(series_id):
    series = RecurringSeries.query.get_or_404(series_id)
    payload = request.get_json(silent=True) or {}

    try:
        if "name" in payload:
            name = (payload["name"] or "").strip()
            if not name:
                raise ValueError("Name is required.")
            series.name = name

        if "kind" in payload:
            series.kind = _parse_enum_field(Kind, payload["kind"], "Kind")

        if "amount" in payload:
            amount = _parse_decimal_field(payload["amount"], "Amount")
            if amount is None:
                raise ValueError("Amount is required.")
            series.amount = amount

        if "cadence_type" in payload:
            series.cadence_type = _parse_enum_field(
                CadenceType, payload["cadence_type"], "Cadence"
            )

        if series.cadence_type == CadenceType.custom:
            custom_interval_value = payload.get(
                "custom_interval_value", series.custom_interval_value
            )
            try:
                custom_interval_value = int(custom_interval_value)
                if custom_interval_value <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                raise ValueError(
                    "Custom interval value is required and must be a positive integer."
                )
            series.custom_interval_value = custom_interval_value
            series.custom_interval_unit = _parse_enum_field(
                CustomIntervalUnit,
                payload.get("custom_interval_unit", series.custom_interval_unit),
                "Custom interval unit",
            )
        else:
            series.custom_interval_value = None
            series.custom_interval_unit = None

        if "start_date" in payload:
            if not payload["start_date"]:
                raise ValueError("Start date is required.")
            series.start_date = _parse_date_param(payload["start_date"], "Start date")

        if "end_date" in payload:
            series.end_date = (
                _parse_date_param(payload["end_date"], "End date")
                if payload["end_date"]
                else None
            )

        if series.end_date is not None and series.end_date < series.start_date:
            raise ValueError("End date must not be before start date.")

        if "notes" in payload:
            series.notes = payload["notes"] or None

        if "kind" in payload or "credit_card_id" in payload:
            series.credit_card_id = _resolve_credit_card_id(
                series.kind, payload.get("credit_card_id"), series.credit_card_id
            )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    Transaction.query.filter_by(
        recurring_series_id=series.id, occurrence_status=OccurrenceStatus.attached
    ).delete(synchronize_session=False)

    horizon = date.today() + timedelta(days=_MATERIALIZE_FUTURE_DAYS)
    range_end = min(series.end_date, horizon) if series.end_date is not None else horizon
    occurrence_dates = generate_occurrences(series, series.start_date, range_end)

    for occurrence_date in occurrence_dates:
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

    return jsonify(
        {
            "id": series.id,
            "name": series.name,
            "kind": series.kind.value,
            "amount": str(series.amount),
            "cadence_type": series.cadence_type.value,
            "custom_interval_value": series.custom_interval_value,
            "custom_interval_unit": (
                series.custom_interval_unit.value
                if series.custom_interval_unit
                else None
            ),
            "start_date": series.start_date.isoformat(),
            "end_date": series.end_date.isoformat() if series.end_date else None,
            "notes": series.notes,
            "credit_card_id": series.credit_card_id,
            "occurrences_created": len(occurrence_dates),
        }
    )


@transactions_bp.route("/series/<int:series_id>", methods=["DELETE"])
@login_required
def delete_series(series_id):
    series = RecurringSeries.query.get_or_404(series_id)

    Transaction.query.filter_by(recurring_series_id=series.id).filter(
        Transaction.occurrence_status.in_(
            [OccurrenceStatus.attached, OccurrenceStatus.skipped]
        )
    ).delete(synchronize_session=False)

    Transaction.query.filter_by(
        recurring_series_id=series.id, occurrence_status=OccurrenceStatus.detached
    ).update(
        {"recurring_series_id": None, "occurrence_status": None},
        synchronize_session=False,
    )

    db.session.delete(series)
    db.session.commit()

    return jsonify({"deleted": True, "id": series_id})


def _serialize_override(override):
    return {
        "id": override.id,
        "credit_card_id": override.credit_card_id,
        "due_date": override.due_date.isoformat(),
        "amount": str(override.amount),
        "notes": override.notes,
    }


@transactions_bp.route("/credit-due-overrides", methods=["PUT"])
@login_required
def set_credit_due_override():
    """Set (create or replace) the payment-due override for a (card, due_date).

    Overrides the computed statement-period sum shown on a payment-due row
    with a manual amount (see specs.md § "Credit card payment logic").
    """
    payload = request.get_json(silent=True) or {}

    try:
        credit_card_id = payload.get("credit_card_id")
        if not CreditCard.query.get(credit_card_id):
            raise ValueError("Credit card not found.")
        due_date = _parse_date_param(payload.get("due_date"), "Due date")
        amount = _parse_decimal_field(payload.get("amount"), "Amount")
        if amount is None:
            raise ValueError("Amount is required.")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    override = CreditDueOverride.query.filter_by(
        credit_card_id=credit_card_id, due_date=due_date
    ).first()
    if override is None:
        override = CreditDueOverride(credit_card_id=credit_card_id, due_date=due_date)
        db.session.add(override)
    override.amount = amount
    override.notes = (payload.get("notes") or "").strip() or None

    db.session.commit()

    return jsonify(_serialize_override(override))


@transactions_bp.route("/credit-due-overrides", methods=["DELETE"])
@login_required
def clear_credit_due_override():
    """Clear a payment-due override, reverting that (card, due_date) row to its
    computed estimate."""
    try:
        credit_card_id = request.args.get("credit_card_id", type=int)
        due_date = _parse_date_param(request.args.get("due_date", ""), "Due date")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    override = CreditDueOverride.query.filter_by(
        credit_card_id=credit_card_id, due_date=due_date
    ).first()
    if override is not None:
        db.session.delete(override)
        db.session.commit()

    return jsonify({"deleted": True})


@transactions_bp.route("/<int:transaction_id>", methods=["PATCH"])
@login_required
def update(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    payload = request.get_json(silent=True) or {}

    try:
        if "name" in payload:
            name = (payload["name"] or "").strip()
            if not name:
                raise ValueError("Name is required.")
            transaction.name = name

        if "kind" in payload:
            transaction.kind = _parse_enum_field(Kind, payload["kind"], "Kind")

        if "amount" in payload:
            amount = _parse_decimal_field(payload["amount"], "Amount")
            if amount is None:
                raise ValueError("Amount is required.")
            transaction.amount = amount

        if "date" in payload:
            transaction.date = _parse_date_param(payload["date"], "Date")

        if "notes" in payload:
            transaction.notes = payload["notes"] or None

        if "kind" in payload or "credit_card_id" in payload:
            transaction.credit_card_id = _resolve_credit_card_id(
                transaction.kind, payload.get("credit_card_id"), transaction.credit_card_id
            )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if (
        transaction.recurring_series_id is not None
        and transaction.occurrence_status == OccurrenceStatus.attached
    ):
        transaction.occurrence_status = OccurrenceStatus.detached

    db.session.commit()

    return jsonify(
        {
            "id": transaction.id,
            "name": transaction.name,
            "date": transaction.date.isoformat(),
            "kind": transaction.kind.value,
            "amount": str(transaction.amount),
            "notes": transaction.notes,
            "credit_card_id": transaction.credit_card_id,
            "recurring_series_id": transaction.recurring_series_id,
            "occurrence_status": (
                transaction.occurrence_status.value
                if transaction.occurrence_status
                else None
            ),
        }
    )


@transactions_bp.route("/<int:transaction_id>/skip", methods=["POST"])
@login_required
def skip(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)

    if transaction.recurring_series_id is None:
        return jsonify({"error": "Only recurring occurrences can be skipped."}), 400

    transaction.occurrence_status = OccurrenceStatus.skipped
    db.session.commit()

    return jsonify(
        {
            "id": transaction.id,
            "occurrence_status": transaction.occurrence_status.value,
        }
    )


@transactions_bp.route("/<int:transaction_id>/unskip", methods=["POST"])
@login_required
def unskip(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)

    if transaction.occurrence_status != OccurrenceStatus.skipped:
        return jsonify({"error": "Transaction is not currently skipped."}), 400

    transaction.occurrence_status = OccurrenceStatus.attached
    db.session.commit()

    return jsonify(
        {
            "id": transaction.id,
            "occurrence_status": transaction.occurrence_status.value,
        }
    )


@transactions_bp.route("/<int:transaction_id>", methods=["DELETE"])
@login_required
def delete(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)

    if (
        transaction.recurring_series_id is not None
        and transaction.occurrence_status == OccurrenceStatus.attached
    ):
        transaction.occurrence_status = OccurrenceStatus.detached
        db.session.commit()
        return jsonify(
            {
                "deleted": False,
                "id": transaction.id,
                "occurrence_status": transaction.occurrence_status.value,
            }
        )

    db.session.delete(transaction)
    db.session.commit()
    return jsonify({"deleted": True, "id": transaction_id})

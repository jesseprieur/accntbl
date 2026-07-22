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
from app.models import CheckingAccount, CreditCardSettings, OccurrenceStatus, Transaction
from app.services.running_total import compute_running_total

transactions_bp = Blueprint("transactions", __name__, url_prefix="/transactions")

_DEFAULT_PAST_DAYS = 30
_DEFAULT_FUTURE_DAYS = 90


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

    history = Transaction.query.filter(Transaction.date <= end).order_by(
        Transaction.date
    ).all()

    checking_accounts = CheckingAccount.query.all()
    credit_card_settings = CreditCardSettings.query.first()

    full_range_start = min((t.date for t in history), default=start)
    full_range_start = min(full_range_start, start)

    ledger = compute_running_total(
        checking_accounts, history, credit_card_settings, full_range_start, end
    )

    rows = [
        {
            "id": row.transaction.id if row.transaction is not None else None,
            "name": row.name,
            "date": row.date.isoformat(),
            "cash_amount": str(row.cash_amount),
            "credit_amount": (
                str(row.transaction.credit_amount)
                if row.transaction is not None and row.transaction.credit_amount
                else None
            ),
            "notes": row.transaction.notes if row.transaction is not None else None,
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
        }
        for row in ledger
        if start <= row.date <= end
    ]

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

        cash_amount = _parse_decimal_field(payload.get("cash_amount"), "Cash amount")
        credit_amount = _parse_decimal_field(payload.get("credit_amount"), "Credit amount")
        notes = payload.get("notes") or None
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    transaction = Transaction(
        name=name,
        cash_amount=cash_amount,
        credit_amount=credit_amount,
        date=txn_date,
        notes=notes,
    )
    db.session.add(transaction)
    db.session.commit()

    return jsonify(
        {
            "id": transaction.id,
            "name": transaction.name,
            "date": transaction.date.isoformat(),
            "cash_amount": str(transaction.cash_amount) if transaction.cash_amount is not None else None,
            "credit_amount": str(transaction.credit_amount) if transaction.credit_amount is not None else None,
            "notes": transaction.notes,
            "recurring_series_id": transaction.recurring_series_id,
            "occurrence_status": None,
        }
    ), 201


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

        if "cash_amount" in payload:
            transaction.cash_amount = _parse_decimal_field(
                payload["cash_amount"], "Cash amount"
            )

        if "credit_amount" in payload:
            transaction.credit_amount = _parse_decimal_field(
                payload["credit_amount"], "Credit amount"
            )

        if "date" in payload:
            transaction.date = _parse_date_param(payload["date"], "Date")

        if "notes" in payload:
            transaction.notes = payload["notes"] or None
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
            "cash_amount": str(transaction.cash_amount) if transaction.cash_amount is not None else None,
            "credit_amount": str(transaction.credit_amount) if transaction.credit_amount is not None else None,
            "notes": transaction.notes,
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

    if transaction.recurring_series_id is not None:
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

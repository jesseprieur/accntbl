"""Paginated transaction window endpoint.

Returns a date-bounded slice of the ledger (real `transactions` rows merged
with virtual credit-card payment-due rows), with running totals computed
from the full transaction history up to the window's end so that a window
that doesn't start at the beginning of time still reports a correct running
total. See specs.md's "Running total calculation" and "Main table view".
"""
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request

from app.auth import login_required
from app.models import CheckingAccount, CreditCardSettings, Transaction
from app.services.running_total import compute_running_total

transactions_bp = Blueprint("transactions", __name__, url_prefix="/transactions")

_DEFAULT_PAST_DAYS = 30
_DEFAULT_FUTURE_DAYS = 90


def _parse_date_param(value, field_label):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"{field_label} must be a valid YYYY-MM-DD date.")


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

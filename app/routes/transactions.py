"""Transaction CRUD + the paginated window endpoint.

`window` returns a date-bounded slice of the ledger (real `transactions`
rows merged with virtual credit-card payment-due rows), with running totals
computed from the full transaction history up to the window's end so that
a window that doesn't start at the beginning of time still reports a
correct running total. See specs.md's "Running total calculation" and
"Main table view". Recurring-series CRUD lives in
`app.routes.recurring_series`; credit-due-override CRUD lives in
`app.routes.credit_cards`.
"""
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import (
    CheckingAccount,
    CreditCard,
    CreditDueOverride,
    Kind,
    NeedsWantsSavings,
    OccurrenceStatus,
    Transaction,
)
from app.routes.auth import login_required
from app.services.parsing import (
    parse_date_param,
    parse_decimal_field,
    parse_enum_field,
    resolve_category_id,
    resolve_credit_card_id,
)
from app.services.running_total import compute_running_total

transactions_bp = Blueprint("transactions", __name__, url_prefix="/transactions")

_DEFAULT_PAST_DAYS = 30
_DEFAULT_FUTURE_DAYS = 90


@transactions_bp.route("/window", methods=["GET"])
@login_required
def window():
    today = date.today()

    try:
        start = (
            parse_date_param(request.args["start"], "start")
            if "start" in request.args
            else today - timedelta(days=_DEFAULT_PAST_DAYS)
        )
        end = (
            parse_date_param(request.args["end"], "end")
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
            "cash_amount": (
                None
                if row.transaction is not None and row.transaction.kind == Kind.credit
                else str(row.cash_amount)
            ),
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
            "needs_wants_savings": (
                row.transaction.needs_wants_savings.value
                if row.transaction is not None
                else None
            ),
            "category_id": (
                row.transaction.category_id if row.transaction is not None else None
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
                "cash_amount": str(t.amount) if t.kind == Kind.cash else None,
                "credit_amount": str(t.amount) if t.kind == Kind.credit else None,
                "notes": t.notes,
                "credit_card_id": t.credit_card_id,
                "recurring_series_id": t.recurring_series_id,
                "occurrence_status": t.occurrence_status.value,
                "needs_wants_savings": t.needs_wants_savings.value,
                "category_id": t.category_id,
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
        txn_date = parse_date_param(payload["date"], "Date")

        kind = parse_enum_field(Kind, payload.get("kind"), "Kind")

        amount = parse_decimal_field(payload.get("amount"), "Amount")
        if amount is None:
            raise ValueError("Amount is required.")

        notes = payload.get("notes") or None

        credit_card_id = resolve_credit_card_id(
            kind, payload.get("credit_card_id"), None
        )

        needs_wants_savings = parse_enum_field(
            NeedsWantsSavings,
            payload.get("needs_wants_savings", NeedsWantsSavings.need.value),
            "Needs/Wants/Savings",
        )
        category_id = resolve_category_id(payload.get("category_id"), None)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    transaction = Transaction(
        name=name,
        kind=kind,
        amount=amount,
        date=txn_date,
        notes=notes,
        credit_card_id=credit_card_id,
        needs_wants_savings=needs_wants_savings,
        category_id=category_id,
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
            "needs_wants_savings": transaction.needs_wants_savings.value,
            "category_id": transaction.category_id,
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

        if "kind" in payload:
            transaction.kind = parse_enum_field(Kind, payload["kind"], "Kind")

        if "amount" in payload:
            amount = parse_decimal_field(payload["amount"], "Amount")
            if amount is None:
                raise ValueError("Amount is required.")
            transaction.amount = amount

        if "date" in payload:
            transaction.date = parse_date_param(payload["date"], "Date")

        if "notes" in payload:
            transaction.notes = payload["notes"] or None

        if "kind" in payload or "credit_card_id" in payload:
            transaction.credit_card_id = resolve_credit_card_id(
                transaction.kind, payload.get("credit_card_id"), transaction.credit_card_id
            )

        if "needs_wants_savings" in payload:
            transaction.needs_wants_savings = parse_enum_field(
                NeedsWantsSavings, payload["needs_wants_savings"], "Needs/Wants/Savings"
            )

        if "category_id" in payload:
            transaction.category_id = resolve_category_id(
                payload.get("category_id"), transaction.category_id
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
            "needs_wants_savings": transaction.needs_wants_savings.value,
            "category_id": transaction.category_id,
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

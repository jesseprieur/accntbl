"""Credit card CRUD (rendered on the Settings page) plus credit-due-override
CRUD (used from the main table's payment-due rows) — both are credit-card
concerns, so they share this blueprint even though their URL paths sit
under different prefixes. See specs.md's `credit_cards` data model section
and "Credit card payment logic".
"""
from flask import Blueprint, flash, jsonify, redirect, request, url_for

from app.extensions import db
from app.models import CreditCard, CreditDueOverride
from app.routes.auth import login_required
from app.services.credit_card import compute_starting_balance_due_date
from app.services.parsing import parse_date_param, parse_decimal_field

credit_cards_bp = Blueprint("credit_cards", __name__)


def _parse_int(value, field_label):
    try:
        return int(value)
    except (ValueError, TypeError):
        raise ValueError(f"{field_label} must be a whole number.")


def _parse_credit_card_form(form):
    name = form.get("name", "").strip()
    if not name:
        raise ValueError("Name is required.")
    statement_close_day = _parse_int(
        form.get("statement_close_day", ""), "Statement close day"
    )
    if not 1 <= statement_close_day <= 31:
        raise ValueError("Statement close day must be between 1 and 31.")
    payment_due_offset_days = _parse_int(
        form.get("payment_due_offset_days", ""), "Payment due offset days"
    )

    return {
        "name": name,
        "statement_close_day": statement_close_day,
        "payment_due_offset_days": payment_due_offset_days,
    }


@credit_cards_bp.route("/settings/credit-cards", methods=["POST"])
@login_required
def create():
    try:
        fields = _parse_credit_card_form(request.form)
        starting_balance = parse_decimal_field(
            request.form.get("starting_balance", ""), "Starting balance"
        )
        if starting_balance is None:
            raise ValueError("Starting balance is required.")
        is_first_card = CreditCard.query.count() == 0
        card = CreditCard(
            **fields,
            starting_balance=starting_balance,
            starting_balance_due_date=compute_starting_balance_due_date(
                fields["statement_close_day"], fields["payment_due_offset_days"]
            ),
        )
        db.session.add(card)
        if is_first_card or request.form.get("is_default"):
            db.session.flush()
            CreditCard.set_default(card)
        db.session.commit()
    except ValueError as exc:
        flash(str(exc))

    return redirect(url_for("settings.index"))


@credit_cards_bp.route("/settings/credit-cards/<int:card_id>", methods=["POST"])
@login_required
def update(card_id):
    card = CreditCard.query.get_or_404(card_id)

    try:
        fields = _parse_credit_card_form(request.form)
        card.name = fields["name"]
        card.statement_close_day = fields["statement_close_day"]
        card.payment_due_offset_days = fields["payment_due_offset_days"]
        if request.form.get("is_default"):
            CreditCard.set_default(card)
        db.session.commit()
    except ValueError as exc:
        flash(str(exc))

    return redirect(url_for("settings.index"))


@credit_cards_bp.route("/settings/credit-cards/<int:card_id>/set-default", methods=["POST"])
@login_required
def set_default(card_id):
    card = CreditCard.query.get_or_404(card_id)
    CreditCard.set_default(card)
    db.session.commit()
    return redirect(url_for("settings.index"))


@credit_cards_bp.route("/settings/credit-cards/<int:card_id>/delete", methods=["POST"])
@login_required
def delete(card_id):
    card = CreditCard.query.get_or_404(card_id)

    blocker = card.deletion_blocker()
    if blocker:
        flash(blocker)
    else:
        db.session.delete(card)
        db.session.commit()

    return redirect(url_for("settings.index"))


def _serialize_override(override):
    return {
        "id": override.id,
        "credit_card_id": override.credit_card_id,
        "due_date": override.due_date.isoformat(),
        "amount": str(override.amount),
        "notes": override.notes,
    }


@credit_cards_bp.route("/transactions/credit-due-overrides", methods=["PUT"])
@login_required
def set_due_override():
    """Set (create or replace) the payment-due override for a (card, due_date).

    Overrides the computed statement-period sum shown on a payment-due row
    with a manual amount (see specs.md § "Credit card payment logic").
    """
    payload = request.get_json(silent=True) or {}

    try:
        credit_card_id = payload.get("credit_card_id")
        if not CreditCard.query.get(credit_card_id):
            raise ValueError("Credit card not found.")
        due_date = parse_date_param(payload.get("due_date"), "Due date")
        amount = parse_decimal_field(payload.get("amount"), "Amount")
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


@credit_cards_bp.route("/transactions/credit-due-overrides", methods=["DELETE"])
@login_required
def clear_due_override():
    """Clear a payment-due override, reverting that (card, due_date) row to its
    computed estimate."""
    try:
        credit_card_id = request.args.get("credit_card_id", type=int)
        due_date = parse_date_param(request.args.get("due_date", ""), "Due date")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    override = CreditDueOverride.query.filter_by(
        credit_card_id=credit_card_id, due_date=due_date
    ).first()
    if override is not None:
        db.session.delete(override)
        db.session.commit()

    return jsonify({"deleted": True})

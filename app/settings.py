from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.auth import login_required
from app.extensions import db
from app.models import CheckingAccount, CreditCard
from app.services.credit_card import compute_starting_balance_due_date

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


def _parse_decimal(value, field_label):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        raise ValueError(f"{field_label} must be a number.")


def _parse_date(value, field_label):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise ValueError(f"{field_label} must be a valid date.")


def _parse_int(value, field_label):
    try:
        return int(value)
    except (ValueError, TypeError):
        raise ValueError(f"{field_label} must be a whole number.")


@settings_bp.route("/", methods=["GET"])
@login_required
def index():
    checking_accounts = CheckingAccount.query.order_by(CheckingAccount.id).all()
    credit_cards = CreditCard.query.order_by(CreditCard.id).all()
    return render_template(
        "settings.html",
        checking_accounts=checking_accounts,
        credit_cards=credit_cards,
        today=date.today().isoformat(),
    )


@settings_bp.route("/checking-accounts", methods=["POST"])
@login_required
def create_checking_account():
    try:
        name = request.form.get("name", "").strip()
        if not name:
            raise ValueError("Name is required.")
        starting_balance = _parse_decimal(
            request.form.get("starting_balance", ""), "Starting balance"
        )
        as_of_date = _parse_date(request.form.get("as_of_date", ""), "As-of date")

        db.session.add(
            CheckingAccount(
                name=name, starting_balance=starting_balance, as_of_date=as_of_date
            )
        )
        db.session.commit()
    except ValueError as exc:
        flash(str(exc))

    return redirect(url_for("settings.index"))


@settings_bp.route("/checking-accounts/<int:account_id>", methods=["POST"])
@login_required
def update_checking_account(account_id):
    account = CheckingAccount.query.get_or_404(account_id)

    try:
        name = request.form.get("name", "").strip()
        if not name:
            raise ValueError("Name is required.")
        starting_balance = _parse_decimal(
            request.form.get("starting_balance", ""), "Starting balance"
        )
        as_of_date = _parse_date(request.form.get("as_of_date", ""), "As-of date")

        account.name = name
        account.starting_balance = starting_balance
        account.as_of_date = as_of_date
        db.session.commit()
    except ValueError as exc:
        flash(str(exc))

    return redirect(url_for("settings.index"))


@settings_bp.route("/checking-accounts/<int:account_id>/delete", methods=["POST"])
@login_required
def delete_checking_account(account_id):
    account = CheckingAccount.query.get_or_404(account_id)
    db.session.delete(account)
    db.session.commit()
    return redirect(url_for("settings.index"))


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


@settings_bp.route("/credit-cards", methods=["POST"])
@login_required
def create_credit_card():
    try:
        fields = _parse_credit_card_form(request.form)
        starting_balance = _parse_decimal(
            request.form.get("starting_balance", ""), "Starting balance"
        )
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


@settings_bp.route("/credit-cards/<int:card_id>", methods=["POST"])
@login_required
def update_credit_card(card_id):
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


@settings_bp.route("/credit-cards/<int:card_id>/set-default", methods=["POST"])
@login_required
def set_default_credit_card(card_id):
    card = CreditCard.query.get_or_404(card_id)
    CreditCard.set_default(card)
    db.session.commit()
    return redirect(url_for("settings.index"))


@settings_bp.route("/credit-cards/<int:card_id>/delete", methods=["POST"])
@login_required
def delete_credit_card(card_id):
    card = CreditCard.query.get_or_404(card_id)

    blocker = card.deletion_blocker()
    if blocker:
        flash(blocker)
    else:
        db.session.delete(card)
        db.session.commit()

    return redirect(url_for("settings.index"))

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.auth import login_required
from app.extensions import db
from app.models import CheckingAccount, CreditCardSettings

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
    credit_card = CreditCardSettings.query.first()
    return render_template(
        "settings.html",
        checking_accounts=checking_accounts,
        credit_card=credit_card,
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


@settings_bp.route("/credit-card", methods=["POST"])
@login_required
def update_credit_card():
    try:
        name = request.form.get("name", "").strip()
        if not name:
            raise ValueError("Name is required.")
        statement_close_day = _parse_int(
            request.form.get("statement_close_day", ""), "Statement close day"
        )
        if not 1 <= statement_close_day <= 31:
            raise ValueError("Statement close day must be between 1 and 31.")
        payment_due_offset_days = _parse_int(
            request.form.get("payment_due_offset_days", ""),
            "Payment due offset days",
        )

        starting_balance_raw = request.form.get("starting_balance", "").strip()
        starting_balance = (
            _parse_decimal(starting_balance_raw, "Starting balance")
            if starting_balance_raw
            else None
        )

        credit_card = CreditCardSettings.query.first()
        if credit_card is None:
            credit_card = CreditCardSettings(id=1, name=name)
            db.session.add(credit_card)

        credit_card.name = name
        credit_card.statement_close_day = statement_close_day
        credit_card.payment_due_offset_days = payment_due_offset_days
        credit_card.starting_balance = starting_balance
        db.session.commit()
    except ValueError as exc:
        flash(str(exc))

    return redirect(url_for("settings.index"))

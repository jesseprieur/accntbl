"""Checking account CRUD, rendered as part of the Settings page. See
specs.md's `checking_accounts` data model section.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, request, url_for

from app.extensions import db
from app.models import CheckingAccount
from app.routes.auth import login_required

checking_accounts_bp = Blueprint(
    "checking_accounts", __name__, url_prefix="/settings/checking-accounts"
)


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


@checking_accounts_bp.route("", methods=["POST"])
@login_required
def create():
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


@checking_accounts_bp.route("/<int:account_id>", methods=["POST"])
@login_required
def update(account_id):
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


@checking_accounts_bp.route("/<int:account_id>/delete", methods=["POST"])
@login_required
def delete(account_id):
    account = CheckingAccount.query.get_or_404(account_id)
    db.session.delete(account)
    db.session.commit()
    return redirect(url_for("settings.index"))

"""Statistics page: running-total extremes, Needs/Wants/Savings/Leftover
breakdown, and spend-by-category breakdown. See specs.md's "Statistics
page" section.
"""
from datetime import date

from flask import Blueprint, jsonify, render_template, request

from app.models import Category, CheckingAccount, CreditCard, CreditDueOverride, Transaction
from app.routes.auth import login_required
from app.services.statistics import (
    compute_needs_wants_savings_breakdown,
    compute_running_total_extremes,
    compute_spend_by_category_breakdown,
    month_options,
    parse_month_selection,
    rolling_12_months,
    serialize_category_rows,
    serialize_nws_breakdown,
)

statistics_bp = Blueprint("statistics", __name__, url_prefix="/statistics")


@statistics_bp.route("")
@login_required
def index():
    checking_accounts = CheckingAccount.query.all()
    credit_cards = CreditCard.query.all()
    credit_due_overrides = CreditDueOverride.query.all()
    transactions = Transaction.query.order_by(Transaction.date).all()
    categories = Category.query.order_by(Category.id).all()
    today = date.today()

    extremes = compute_running_total_extremes(
        checking_accounts,
        transactions,
        credit_cards,
        today,
        credit_due_overrides=credit_due_overrides,
    )

    months = rolling_12_months(today)
    selected_month = months[0]
    nws = compute_needs_wants_savings_breakdown(transactions, today, selected_month)
    category_rows = compute_spend_by_category_breakdown(transactions, categories, today, selected_month)

    return render_template(
        "statistics.html",
        extremes=extremes,
        month_options=month_options(months),
        selected_month_value=selected_month.strftime("%Y-%m"),
        needs_wants_savings=serialize_nws_breakdown(nws),
        spend_by_category=serialize_category_rows(category_rows),
    )


@statistics_bp.route("/breakdown")
@login_required
def breakdown():
    today = date.today()
    months = rolling_12_months(today)
    selection = request.args.get("month", months[0].strftime("%Y-%m"))
    month = parse_month_selection(selection, months)

    transactions = Transaction.query.order_by(Transaction.date).all()
    categories = Category.query.order_by(Category.id).all()

    nws = compute_needs_wants_savings_breakdown(transactions, today, month)
    category_rows = compute_spend_by_category_breakdown(transactions, categories, today, month)

    return jsonify(
        {
            "needs_wants_savings": serialize_nws_breakdown(nws),
            "spend_by_category": serialize_category_rows(category_rows),
        }
    )

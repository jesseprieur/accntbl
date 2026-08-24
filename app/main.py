import json
from datetime import date

from flask import Blueprint, jsonify, render_template, request

from app.auth import login_required
from app.models import Category, CheckingAccount, CreditCard, CreditDueOverride, Transaction
from app.services.statistics import (
    compute_needs_wants_savings_breakdown,
    compute_running_total_extremes,
    compute_spend_by_category_breakdown,
    rolling_12_months,
)

main_bp = Blueprint("main", __name__)


def _credit_cards_context():
    cards = CreditCard.query.order_by(CreditCard.id).all()
    default_card = next((card for card in cards if card.is_default), None)
    return {
        "credit_cards": cards,
        "credit_cards_json": json.dumps(
            [{"id": card.id, "name": card.name} for card in cards]
        ),
        "default_credit_card_id": default_card.id if default_card else None,
    }


def _categories_context():
    categories = Category.query.order_by(Category.id).all()
    return {
        "categories": categories,
        "categories_json": json.dumps(
            [
                {"id": category.id, "name": category.name, "icon": category.icon}
                for category in categories
            ]
        ),
    }


@main_bp.route("/")
@login_required
def index():
    return render_template(
        "index.html", **_credit_cards_context(), **_categories_context()
    )


@main_bp.route("/recurring-series")
@login_required
def recurring_series():
    return render_template(
        "recurring_series.html", **_credit_cards_context(), **_categories_context()
    )


def _month_options(months):
    options = [{"value": m.strftime("%Y-%m"), "label": m.strftime("%B %Y")} for m in months]
    options.append({"value": "average", "label": "Average"})
    return options


def _parse_month_selection(value, months):
    if value == "average":
        return None
    for month in months:
        if value == month.strftime("%Y-%m"):
            return month
    return months[0]


def _format_money(value):
    return "${:,.2f}".format(value)


def _format_pct(value):
    return "—" if value is None else "{:.1f}%".format(value)


def _serialize_nws_breakdown(breakdown):
    return {
        "rows": [
            {"label": "Income", "value": _format_money(breakdown.income), "pct": _format_pct(breakdown.pct_income)},
            {"label": "Needs", "value": _format_money(breakdown.needs), "pct": _format_pct(breakdown.pct_needs)},
            {"label": "Wants", "value": _format_money(breakdown.wants), "pct": _format_pct(breakdown.pct_wants)},
            {"label": "Savings", "value": _format_money(breakdown.savings), "pct": _format_pct(breakdown.pct_savings)},
            {"label": "Leftover", "value": _format_money(breakdown.leftover), "pct": _format_pct(breakdown.pct_leftover)},
        ]
    }


def _serialize_category_rows(rows):
    return {
        "rows": [
            {
                "category_id": row.category_id,
                "name": row.name,
                "icon": row.icon,
                "value": _format_money(row.value),
                "pct": _format_pct(row.pct),
            }
            for row in rows
        ]
    }


@main_bp.route("/statistics")
@login_required
def statistics():
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
        month_options=_month_options(months),
        selected_month_value=selected_month.strftime("%Y-%m"),
        needs_wants_savings=_serialize_nws_breakdown(nws),
        spend_by_category=_serialize_category_rows(category_rows),
    )


@main_bp.route("/statistics/breakdown")
@login_required
def statistics_breakdown():
    today = date.today()
    months = rolling_12_months(today)
    selection = request.args.get("month", months[0].strftime("%Y-%m"))
    month = _parse_month_selection(selection, months)

    transactions = Transaction.query.order_by(Transaction.date).all()
    categories = Category.query.order_by(Category.id).all()

    nws = compute_needs_wants_savings_breakdown(transactions, today, month)
    category_rows = compute_spend_by_category_breakdown(transactions, categories, today, month)

    return jsonify(
        {
            "needs_wants_savings": _serialize_nws_breakdown(nws),
            "spend_by_category": _serialize_category_rows(category_rows),
        }
    )

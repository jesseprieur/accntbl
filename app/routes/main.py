"""Page shells: the main table and the Recurring Series page. The
Statistics page shell lives in `app.routes.statistics` alongside its data
routes; the Settings page shell lives in `app.routes.settings`.
"""
import json

from flask import Blueprint, render_template

from app.models import Category, CreditCard
from app.routes.auth import login_required

main_bp = Blueprint("main", __name__)


def credit_cards_context():
    cards = CreditCard.query.order_by(CreditCard.id).all()
    default_card = next((card for card in cards if card.is_default), None)
    return {
        "credit_cards": cards,
        "credit_cards_json": json.dumps(
            [{"id": card.id, "name": card.name} for card in cards]
        ),
        "default_credit_card_id": default_card.id if default_card else None,
    }


def categories_context():
    categories = Category.query.order_by(Category.id).all()
    uncategorized = Category.get_uncategorized()
    return {
        "categories": categories,
        "categories_json": json.dumps(
            [
                {"id": category.id, "name": category.name, "icon": category.icon}
                for category in categories
            ]
        ),
        "default_category_id": uncategorized.id if uncategorized else None,
    }


@main_bp.route("/")
@login_required
def index():
    return render_template("index.html", **credit_cards_context(), **categories_context())


@main_bp.route("/recurring-series")
@login_required
def recurring_series():
    return render_template(
        "recurring_series.html", **credit_cards_context(), **categories_context()
    )

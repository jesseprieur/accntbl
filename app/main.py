import json

from flask import Blueprint, render_template

from app.auth import login_required
from app.models import Category, CreditCard

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
            [{"id": category.id, "name": category.name} for category in categories]
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

import json
from datetime import date

from flask import Blueprint, render_template

from app.auth import login_required
from app.models import CreditCard

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


@main_bp.route("/")
@login_required
def index():
    return render_template(
        "index.html", today=date.today().isoformat(), **_credit_cards_context()
    )


@main_bp.route("/recurring-series")
@login_required
def recurring_series():
    return render_template(
        "recurring_series.html",
        today=date.today().isoformat(),
        **_credit_cards_context(),
    )

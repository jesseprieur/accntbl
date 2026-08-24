"""Settings page shell — aggregates checking accounts, credit cards, and
categories for display. CRUD for each lives in its own blueprint
(`checking_accounts`, `credit_cards`, `categories`, `backup`).
"""
from flask import Blueprint, render_template

from app.models import CATEGORY_ICON_CHOICES, Category, CheckingAccount, CreditCard
from app.routes.auth import login_required

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


@settings_bp.route("/", methods=["GET"])
@login_required
def index():
    checking_accounts = CheckingAccount.query.order_by(CheckingAccount.id).all()
    credit_cards = CreditCard.query.order_by(CreditCard.id).all()
    categories = Category.query.order_by(Category.id).all()
    return render_template(
        "settings.html",
        checking_accounts=checking_accounts,
        credit_cards=credit_cards,
        categories=categories,
        category_icon_choices=CATEGORY_ICON_CHOICES,
    )

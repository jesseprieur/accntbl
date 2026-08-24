"""Shared request-payload parsing/resolution used by the transactions and
recurring_series route blueprints, so both CRUD surfaces validate and
resolve fields the same way.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.models import Category, CreditCard, Kind


def parse_date_param(value, field_label):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"{field_label} must be a valid YYYY-MM-DD date.")


def parse_decimal_field(value, field_label):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{field_label} must be a number.")


def parse_enum_field(enum_cls, value, field_label):
    try:
        return enum_cls(value)
    except ValueError:
        allowed = ", ".join(member.value for member in enum_cls)
        raise ValueError(f"{field_label} must be one of: {allowed}.")


def resolve_credit_card_id(kind, requested_id, existing_id):
    """Resolve `credit_card_id` for a transaction/series being created or edited.

    Cash entities never carry a card. Credit entities keep an explicitly
    requested card (validated to exist), otherwise keep their current card,
    otherwise fall back to the default card.
    """
    if kind == Kind.cash:
        return None

    if requested_id is not None:
        try:
            card_id = int(requested_id)
        except (TypeError, ValueError):
            raise ValueError("Credit card is invalid.")
        if not CreditCard.query.get(card_id):
            raise ValueError("Credit card not found.")
        return card_id

    if existing_id is not None:
        return existing_id

    default_card = CreditCard.query.filter_by(is_default=True).first()
    if default_card is None:
        raise ValueError("A credit card is required; add one in Settings first.")
    return default_card.id


def resolve_category_id(requested_id, existing_id):
    """Resolve `category_id` for a transaction/series being created or edited.

    An explicitly requested category is validated to exist. An explicit
    empty value (the placeholder option) falls back to `Uncategorized`
    (category_id is a required field — see specs.md § `categories`).
    Otherwise the current category is kept, or `Uncategorized` for a new
    record.
    """
    if requested_id == "":
        return Category.get_uncategorized().id

    if requested_id is not None:
        try:
            category_id = int(requested_id)
        except (TypeError, ValueError):
            raise ValueError("Category is invalid.")
        if not Category.query.get(category_id):
            raise ValueError("Category not found.")
        return category_id

    if existing_id is not None:
        return existing_id

    return Category.get_uncategorized().id

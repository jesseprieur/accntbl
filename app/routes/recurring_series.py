"""Recurring series CRUD. See specs.md's `recurring_series` data model and
"Recurring series editing semantics" sections.
"""
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import (
    CadenceType,
    CustomIntervalUnit,
    Kind,
    NeedsWantsSavings,
    OccurrenceStatus,
    RecurringSeries,
    Transaction,
)
from app.routes.auth import login_required
from app.services.amount_logic import resolve_amount
from app.services.parsing import (
    parse_date_param,
    parse_decimal_field,
    parse_enum_field,
    resolve_category_id,
    resolve_credit_card_id,
)
from app.services.recurring import generate_occurrences, per_month_amount

recurring_series_bp = Blueprint(
    "recurring_series", __name__, url_prefix="/transactions/series"
)

_MATERIALIZE_FUTURE_DAYS = 365


def _parse_amount_logic(value):
    """Validate and normalize a `RecurringSeries.amount_logic` payload.

    Returns `None` (plain `amount` applies) or a cleaned dict matching one
    of the shapes documented in `app.services.amount_logic`.
    """
    if not value:
        return None
    if not isinstance(value, dict):
        raise ValueError("Advanced amount logic must be an object.")

    logic_type = value.get("type")

    if logic_type == "conditional":
        rules = value.get("rules") or []
        if not isinstance(rules, list) or not rules:
            raise ValueError("Conditional amount logic requires at least one rule.")
        cleaned_rules = []
        for rule in rules:
            try:
                month = int(rule["until_month"])
                day = int(rule["until_day"])
                date(2000, month, day)  # validates month/day combination
            except (KeyError, TypeError, ValueError):
                raise ValueError("Each conditional rule needs a valid until month/day.")
            year = rule.get("until_year")
            year = int(year) if year not in (None, "") else None
            amount = parse_decimal_field(rule.get("amount"), "Conditional rule amount")
            if amount is None:
                raise ValueError("Each conditional rule needs an amount.")
            cleaned_rules.append(
                {"until_month": month, "until_day": day, "until_year": year, "amount": str(amount)}
            )
        else_amount = parse_decimal_field(value.get("else_amount"), "Else amount")
        return {
            "type": "conditional",
            "rules": cleaned_rules,
            "else_amount": str(else_amount) if else_amount is not None else None,
        }

    if logic_type == "escalating":
        adjustment_type = value.get("adjustment_type")
        if adjustment_type not in ("amount", "percentage"):
            raise ValueError(
                "Escalating amount logic adjustment type must be 'amount' or 'percentage'."
            )
        magnitude = parse_decimal_field(value.get("value"), "Escalation value")
        if magnitude is None:
            raise ValueError("Escalation value must be a number.")
        return {
            "type": "escalating",
            "adjustment_type": adjustment_type,
            "value": str(magnitude),
        }

    raise ValueError("Advanced amount logic type must be 'conditional' or 'escalating'.")


def _serialize_series(series):
    return {
        "id": series.id,
        "name": series.name,
        "kind": series.kind.value,
        "amount": str(series.amount),
        "cadence_type": series.cadence_type.value,
        "custom_interval_value": series.custom_interval_value,
        "custom_interval_unit": (
            series.custom_interval_unit.value if series.custom_interval_unit else None
        ),
        "start_date": series.start_date.isoformat(),
        "end_date": series.end_date.isoformat() if series.end_date else None,
        "notes": series.notes,
        "credit_card_id": series.credit_card_id,
        "amount_logic": series.amount_logic,
        "needs_wants_savings": series.needs_wants_savings.value,
        "category_id": series.category_id,
    }


@recurring_series_bp.route("", methods=["POST"])
@login_required
def create_series():
    payload = request.get_json(silent=True) or {}

    try:
        name = (payload.get("name") or "").strip()
        if not name:
            raise ValueError("Name is required.")

        kind = parse_enum_field(Kind, payload.get("kind"), "Kind")

        amount = parse_decimal_field(payload.get("amount"), "Amount")
        if amount is None:
            raise ValueError("Amount is required.")

        cadence_type = parse_enum_field(
            CadenceType, payload.get("cadence_type"), "Cadence"
        )

        custom_interval_value = None
        custom_interval_unit = None
        if cadence_type == CadenceType.custom:
            custom_interval_value = payload.get("custom_interval_value")
            try:
                custom_interval_value = int(custom_interval_value)
                if custom_interval_value <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                raise ValueError(
                    "Custom interval value is required and must be a positive integer."
                )
            custom_interval_unit = parse_enum_field(
                CustomIntervalUnit,
                payload.get("custom_interval_unit"),
                "Custom interval unit",
            )

        if "start_date" not in payload or not payload["start_date"]:
            raise ValueError("Start date is required.")
        start_date = parse_date_param(payload["start_date"], "Start date")

        end_date = None
        if payload.get("end_date"):
            end_date = parse_date_param(payload["end_date"], "End date")
            if end_date < start_date:
                raise ValueError("End date must not be before start date.")

        notes = payload.get("notes") or None

        credit_card_id = resolve_credit_card_id(
            kind, payload.get("credit_card_id"), None
        )

        amount_logic = _parse_amount_logic(payload.get("amount_logic"))

        needs_wants_savings = parse_enum_field(
            NeedsWantsSavings,
            payload.get("needs_wants_savings", NeedsWantsSavings.need.value),
            "Needs/Wants/Savings",
        )
        category_id = resolve_category_id(payload.get("category_id"), None)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    series = RecurringSeries(
        name=name,
        kind=kind,
        amount=amount,
        cadence_type=cadence_type,
        custom_interval_value=custom_interval_value,
        custom_interval_unit=custom_interval_unit,
        start_date=start_date,
        end_date=end_date,
        notes=notes,
        credit_card_id=credit_card_id,
        amount_logic=amount_logic,
        needs_wants_savings=needs_wants_savings,
        category_id=category_id,
    )
    db.session.add(series)
    db.session.flush()

    horizon = date.today() + timedelta(days=_MATERIALIZE_FUTURE_DAYS)
    range_end = min(end_date, horizon) if end_date is not None else horizon
    occurrence_dates = generate_occurrences(series, start_date, range_end)

    for occurrence_date in occurrence_dates:
        db.session.add(
            Transaction(
                name=series.name,
                kind=kind,
                amount=resolve_amount(series, occurrence_date),
                date=occurrence_date,
                notes=notes,
                recurring_series_id=series.id,
                occurrence_status=OccurrenceStatus.attached,
                credit_card_id=credit_card_id,
                needs_wants_savings=series.needs_wants_savings,
                category_id=series.category_id,
            )
        )

    db.session.commit()

    return jsonify(dict(_serialize_series(series), occurrences_created=len(occurrence_dates))), 201


@recurring_series_bp.route("", methods=["GET"])
@login_required
def list_series():
    series = RecurringSeries.query.order_by(RecurringSeries.name).all()
    return jsonify(
        {
            "series": [
                dict(_serialize_series(s), per_month=str(per_month_amount(s)))
                for s in series
            ]
        }
    )


@recurring_series_bp.route("/<int:series_id>", methods=["GET"])
@login_required
def get_series(series_id):
    series = RecurringSeries.query.get_or_404(series_id)
    return jsonify(_serialize_series(series))


@recurring_series_bp.route("/<int:series_id>", methods=["PATCH"])
@login_required
def update_series(series_id):
    series = RecurringSeries.query.get_or_404(series_id)
    payload = request.get_json(silent=True) or {}

    try:
        if "name" in payload:
            name = (payload["name"] or "").strip()
            if not name:
                raise ValueError("Name is required.")
            series.name = name

        if "kind" in payload:
            series.kind = parse_enum_field(Kind, payload["kind"], "Kind")

        if "amount" in payload:
            amount = parse_decimal_field(payload["amount"], "Amount")
            if amount is None:
                raise ValueError("Amount is required.")
            series.amount = amount

        if "cadence_type" in payload:
            series.cadence_type = parse_enum_field(
                CadenceType, payload["cadence_type"], "Cadence"
            )

        if series.cadence_type == CadenceType.custom:
            custom_interval_value = payload.get(
                "custom_interval_value", series.custom_interval_value
            )
            try:
                custom_interval_value = int(custom_interval_value)
                if custom_interval_value <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                raise ValueError(
                    "Custom interval value is required and must be a positive integer."
                )
            series.custom_interval_value = custom_interval_value
            series.custom_interval_unit = parse_enum_field(
                CustomIntervalUnit,
                payload.get("custom_interval_unit", series.custom_interval_unit),
                "Custom interval unit",
            )
        else:
            series.custom_interval_value = None
            series.custom_interval_unit = None

        if "start_date" in payload:
            if not payload["start_date"]:
                raise ValueError("Start date is required.")
            series.start_date = parse_date_param(payload["start_date"], "Start date")

        if "end_date" in payload:
            series.end_date = (
                parse_date_param(payload["end_date"], "End date")
                if payload["end_date"]
                else None
            )

        if series.end_date is not None and series.end_date < series.start_date:
            raise ValueError("End date must not be before start date.")

        if "notes" in payload:
            series.notes = payload["notes"] or None

        if "kind" in payload or "credit_card_id" in payload:
            series.credit_card_id = resolve_credit_card_id(
                series.kind, payload.get("credit_card_id"), series.credit_card_id
            )

        if "amount_logic" in payload:
            series.amount_logic = _parse_amount_logic(payload["amount_logic"])

        if "needs_wants_savings" in payload:
            series.needs_wants_savings = parse_enum_field(
                NeedsWantsSavings, payload["needs_wants_savings"], "Needs/Wants/Savings"
            )

        if "category_id" in payload:
            series.category_id = resolve_category_id(
                payload.get("category_id"), series.category_id
            )

        effective_date = None
        if payload.get("save_mode") == "future":
            if not payload.get("effective_date"):
                raise ValueError(
                    "An effective date is required to save changes for future occurrences only."
                )
            effective_date = parse_date_param(
                payload["effective_date"], "Effective date"
            )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

    attached_query = Transaction.query.filter_by(
        recurring_series_id=series.id, occurrence_status=OccurrenceStatus.attached
    )

    if effective_date is not None:
        attached_query.filter(Transaction.date <= effective_date).update(
            {"occurrence_status": OccurrenceStatus.detached},
            synchronize_session=False,
        )
        attached_query.filter(Transaction.date > effective_date).delete(
            synchronize_session=False
        )
        regen_start = max(series.start_date, effective_date + timedelta(days=1))
    else:
        attached_query.delete(synchronize_session=False)
        regen_start = series.start_date

    horizon = date.today() + timedelta(days=_MATERIALIZE_FUTURE_DAYS)
    range_end = min(series.end_date, horizon) if series.end_date is not None else horizon
    occurrence_dates = (
        generate_occurrences(series, regen_start, range_end)
        if regen_start <= range_end
        else []
    )

    for occurrence_date in occurrence_dates:
        db.session.add(
            Transaction(
                name=series.name,
                kind=series.kind,
                amount=resolve_amount(series, occurrence_date),
                date=occurrence_date,
                notes=series.notes,
                recurring_series_id=series.id,
                occurrence_status=OccurrenceStatus.attached,
                credit_card_id=series.credit_card_id,
                needs_wants_savings=series.needs_wants_savings,
                category_id=series.category_id,
            )
        )

    db.session.commit()

    return jsonify(dict(_serialize_series(series), occurrences_created=len(occurrence_dates)))


@recurring_series_bp.route("/<int:series_id>", methods=["DELETE"])
@login_required
def delete_series(series_id):
    series = RecurringSeries.query.get_or_404(series_id)

    Transaction.query.filter_by(recurring_series_id=series.id).filter(
        Transaction.occurrence_status.in_(
            [OccurrenceStatus.attached, OccurrenceStatus.skipped]
        )
    ).delete(synchronize_session=False)

    Transaction.query.filter_by(
        recurring_series_id=series.id, occurrence_status=OccurrenceStatus.detached
    ).update(
        {"recurring_series_id": None, "occurrence_status": None},
        synchronize_session=False,
    )

    db.session.delete(series)
    db.session.commit()

    return jsonify({"deleted": True, "id": series_id})

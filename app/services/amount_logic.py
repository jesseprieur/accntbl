"""Advanced per-occurrence amount logic for recurring series.

`RecurringSeries.amount_logic` is an optional JSON blob that overrides the
plain `series.amount` used for a materialized occurrence. Two shapes are
supported (see specs.md's "Advanced amount logic" section):

- `{"type": "conditional", "rules": [{"until_month", "until_day",
  "until_year" (optional)}, "amount"], ...], "else_amount": "..."}`
  Evaluated like an if/elseif/else chain, in list order: the first rule
  whose threshold date (built from until_month/until_day, and until_year if
  given, else the occurrence's own year) is on-or-before the occurrence
  date wins; if none match, `else_amount` is used.
- `{"type": "escalating", "direction": "increase"|"decrease",
  "adjustment_type": "amount"|"percentage", "value": "..."}`
  Adjusts the magnitude of `series.amount` per occurrence index (0 for the
  first occurrence on/after `series.start_date`, 1 for the next, ...),
  linearly for "amount" or compounding for "percentage", floored at zero,
  then reapplies the original sign.

Both fall back to plain `series.amount` when `amount_logic` is unset or its
type is unrecognized.
"""
from datetime import date
from decimal import Decimal

from app.services.recurring import generate_occurrences

_CENTS = Decimal("0.01")


def _threshold_date(rule, occurrence_date):
    year = rule.get("until_year") or occurrence_date.year
    return date(year, int(rule["until_month"]), int(rule["until_day"]))


def _resolve_conditional(series, logic, occurrence_date):
    for rule in logic.get("rules") or []:
        if occurrence_date >= _threshold_date(rule, occurrence_date):
            return Decimal(str(rule["amount"])).quantize(_CENTS)

    else_amount = logic.get("else_amount")
    if else_amount is not None:
        return Decimal(str(else_amount)).quantize(_CENTS)
    return series.amount


def _occurrence_index(series, occurrence_date):
    """0-based position of `occurrence_date` among the series' occurrences,
    counting from `series.start_date`."""
    occurrences = generate_occurrences(series, series.start_date, occurrence_date)
    return len(occurrences) - 1


def _resolve_escalating(series, logic, occurrence_date):
    index = _occurrence_index(series, occurrence_date)
    magnitude = abs(series.amount)
    value = Decimal(str(logic["value"]))
    sign = Decimal("-1") if logic.get("direction") == "decrease" else Decimal("1")

    if logic.get("adjustment_type") == "percentage":
        factor = (Decimal("1") + sign * value / Decimal("100")) ** index
        magnitude = magnitude * factor
    else:
        magnitude = magnitude + sign * value * index

    magnitude = max(magnitude, Decimal("0"))
    result_sign = Decimal("-1") if series.amount < 0 else Decimal("1")
    return (result_sign * magnitude).quantize(_CENTS)


def resolve_amount(series, occurrence_date):
    """Return the amount that should apply to `series`'s occurrence dated
    `occurrence_date`, honoring `series.amount_logic` when present."""
    logic = series.amount_logic
    if not logic:
        return series.amount

    logic_type = logic.get("type")
    if logic_type == "conditional":
        return _resolve_conditional(series, logic, occurrence_date)
    if logic_type == "escalating":
        return _resolve_escalating(series, logic, occurrence_date)
    return series.amount

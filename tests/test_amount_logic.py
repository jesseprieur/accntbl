import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

from app.models import CadenceType
from app.services.amount_logic import resolve_amount


def make_series(amount, amount_logic=None, cadence_type=CadenceType.monthly,
                 start_date=dt.date(2026, 1, 1), end_date=None):
    return SimpleNamespace(
        amount=amount,
        amount_logic=amount_logic,
        cadence_type=cadence_type,
        start_date=start_date,
        end_date=end_date,
        custom_interval_value=None,
        custom_interval_unit=None,
    )


def test_resolve_amount_returns_plain_amount_when_no_logic():
    series = make_series(Decimal("100.00"))
    assert resolve_amount(series, dt.date(2026, 3, 1)) == Decimal("100.00")


def test_conditional_matches_first_rule_whose_threshold_has_passed():
    series = make_series(
        Decimal("100.00"),
        amount_logic={
            "type": "conditional",
            "rules": [
                {"until_month": 7, "until_day": 1, "amount": "300.00"},
                {"until_month": 4, "until_day": 1, "amount": "200.00"},
            ],
            "else_amount": "100.00",
        },
    )
    assert resolve_amount(series, dt.date(2026, 8, 1)) == Decimal("300.00")
    assert resolve_amount(series, dt.date(2026, 5, 1)) == Decimal("200.00")
    assert resolve_amount(series, dt.date(2026, 2, 1)) == Decimal("100.00")


def test_conditional_falls_back_to_else_amount_when_no_rule_matches():
    series = make_series(
        Decimal("50.00"),
        amount_logic={
            "type": "conditional",
            "rules": [{"until_month": 12, "until_day": 31, "amount": "999.00"}],
            "else_amount": "10.00",
        },
    )
    assert resolve_amount(series, dt.date(2026, 1, 1)) == Decimal("10.00")


def test_conditional_falls_back_to_series_amount_when_no_else_amount():
    series = make_series(
        Decimal("50.00"),
        amount_logic={
            "type": "conditional",
            "rules": [{"until_month": 12, "until_day": 31, "amount": "999.00"}],
        },
    )
    assert resolve_amount(series, dt.date(2026, 1, 1)) == Decimal("50.00")


def test_conditional_rule_with_explicit_year_is_a_one_time_threshold():
    series = make_series(
        Decimal("50.00"),
        amount_logic={
            "type": "conditional",
            "rules": [{"until_month": 6, "until_day": 1, "until_year": 2027, "amount": "999.00"}],
            "else_amount": "50.00",
        },
    )
    # Same month/day a year earlier must not match a rule pinned to 2027.
    assert resolve_amount(series, dt.date(2026, 6, 15)) == Decimal("50.00")
    assert resolve_amount(series, dt.date(2027, 6, 15)) == Decimal("999.00")


def test_escalating_increase_by_flat_amount_each_occurrence():
    series = make_series(
        Decimal("-100.00"),
        amount_logic={"type": "escalating", "adjustment_type": "amount", "value": "10.00"},
        cadence_type=CadenceType.monthly,
        start_date=dt.date(2026, 1, 1),
    )
    assert resolve_amount(series, dt.date(2026, 1, 1)) == Decimal("-100.00")
    assert resolve_amount(series, dt.date(2026, 2, 1)) == Decimal("-110.00")
    assert resolve_amount(series, dt.date(2026, 3, 1)) == Decimal("-120.00")


def test_escalating_decrease_by_percentage_compounds_and_preserves_sign():
    series = make_series(
        Decimal("-100.00"),
        amount_logic={"type": "escalating", "adjustment_type": "percentage", "value": "-10"},
        cadence_type=CadenceType.monthly,
        start_date=dt.date(2026, 1, 1),
    )
    assert resolve_amount(series, dt.date(2026, 1, 1)) == Decimal("-100.00")
    assert resolve_amount(series, dt.date(2026, 2, 1)) == Decimal("-90.00")
    assert resolve_amount(series, dt.date(2026, 3, 1)) == Decimal("-81.00")


def test_escalating_decrease_floors_at_zero_instead_of_going_positive():
    series = make_series(
        Decimal("-10.00"),
        amount_logic={"type": "escalating", "adjustment_type": "amount", "value": "-100.00"},
        cadence_type=CadenceType.monthly,
        start_date=dt.date(2026, 1, 1),
    )
    assert resolve_amount(series, dt.date(2026, 2, 1)) == Decimal("0.00")


def test_unrecognized_logic_type_falls_back_to_plain_amount():
    series = make_series(Decimal("75.00"), amount_logic={"type": "bogus"})
    assert resolve_amount(series, dt.date(2026, 1, 1)) == Decimal("75.00")

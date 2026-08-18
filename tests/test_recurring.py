import datetime as dt
from types import SimpleNamespace

import pytest

from decimal import Decimal

from app.models import CadenceType, CustomIntervalUnit
from app.services.recurring import generate_occurrences, per_month_amount


def make_series(
    cadence_type,
    start_date,
    end_date=None,
    custom_interval_value=None,
    custom_interval_unit=None,
):
    return SimpleNamespace(
        cadence_type=cadence_type,
        start_date=start_date,
        end_date=end_date,
        custom_interval_value=custom_interval_value,
        custom_interval_unit=custom_interval_unit,
    )


def test_weekly_within_range():
    series = make_series(CadenceType.weekly, dt.date(2026, 1, 1))
    dates = generate_occurrences(series, dt.date(2026, 1, 1), dt.date(2026, 1, 22))
    assert dates == [
        dt.date(2026, 1, 1),
        dt.date(2026, 1, 8),
        dt.date(2026, 1, 15),
        dt.date(2026, 1, 22),
    ]


def test_biweekly_range_starting_after_series_start_jumps_ahead():
    series = make_series(CadenceType.biweekly, dt.date(2026, 1, 1))
    # Range starts well after the series' own start_date; make sure the
    # jump-ahead arithmetic still lands on the correct cadence days rather
    # than iterating from start_date one interval at a time.
    dates = generate_occurrences(series, dt.date(2027, 1, 1), dt.date(2027, 1, 31))
    assert all((d - dt.date(2026, 1, 1)).days % 14 == 0 for d in dates)
    assert dates == sorted(dates)
    assert len(dates) > 0


def test_monthly_clamps_day_to_shorter_months():
    series = make_series(CadenceType.monthly, dt.date(2026, 1, 31))
    dates = generate_occurrences(series, dt.date(2026, 1, 1), dt.date(2026, 4, 30))
    # Jan 31 -> Feb has no 31st, clamp to Feb 28 (2026 is not a leap year).
    assert dates == [
        dt.date(2026, 1, 31),
        dt.date(2026, 2, 28),
        dt.date(2026, 3, 31),
        dt.date(2026, 4, 30),
    ]


def test_quarterly():
    series = make_series(CadenceType.quarterly, dt.date(2026, 1, 15))
    dates = generate_occurrences(series, dt.date(2026, 1, 1), dt.date(2026, 12, 31))
    assert dates == [
        dt.date(2026, 1, 15),
        dt.date(2026, 4, 15),
        dt.date(2026, 7, 15),
        dt.date(2026, 10, 15),
    ]


def test_yearly():
    series = make_series(CadenceType.yearly, dt.date(2024, 2, 29))
    dates = generate_occurrences(series, dt.date(2024, 1, 1), dt.date(2027, 12, 31))
    # 2024 is a leap year; non-leap years clamp Feb 29 -> Feb 28.
    assert dates == [
        dt.date(2024, 2, 29),
        dt.date(2025, 2, 28),
        dt.date(2026, 2, 28),
        dt.date(2027, 2, 28),
    ]


def test_semi_monthly_produces_two_per_month():
    series = make_series(CadenceType.semi_monthly, dt.date(2026, 1, 1))
    dates = generate_occurrences(series, dt.date(2026, 1, 1), dt.date(2026, 2, 28))
    assert dates == [
        dt.date(2026, 1, 15),
        dt.date(2026, 1, 31),
        dt.date(2026, 2, 15),
        dt.date(2026, 2, 28),
    ]


def test_semi_monthly_with_high_day_start_date_still_produces_two_per_month():
    # Regression test: start_date on the 31st previously collided with the
    # end-of-month candidate and silently dropped the 15th occurrence.
    series = make_series(CadenceType.semi_monthly, dt.date(2026, 1, 31))
    dates = generate_occurrences(series, dt.date(2026, 1, 1), dt.date(2026, 3, 31))
    assert dates == [
        dt.date(2026, 1, 31),
        dt.date(2026, 2, 15),
        dt.date(2026, 2, 28),
        dt.date(2026, 3, 15),
        dt.date(2026, 3, 31),
    ]


def test_custom_days():
    series = make_series(
        CadenceType.custom,
        dt.date(2026, 1, 1),
        custom_interval_value=10,
        custom_interval_unit=CustomIntervalUnit.days,
    )
    dates = generate_occurrences(series, dt.date(2026, 1, 1), dt.date(2026, 1, 31))
    assert dates == [
        dt.date(2026, 1, 1),
        dt.date(2026, 1, 11),
        dt.date(2026, 1, 21),
        dt.date(2026, 1, 31),
    ]


def test_custom_months():
    series = make_series(
        CadenceType.custom,
        dt.date(2026, 1, 1),
        custom_interval_value=2,
        custom_interval_unit=CustomIntervalUnit.months,
    )
    dates = generate_occurrences(series, dt.date(2026, 1, 1), dt.date(2026, 12, 31))
    assert dates == [
        dt.date(2026, 1, 1),
        dt.date(2026, 3, 1),
        dt.date(2026, 5, 1),
        dt.date(2026, 7, 1),
        dt.date(2026, 9, 1),
        dt.date(2026, 11, 1),
    ]


def test_custom_without_unit_raises():
    series = make_series(
        CadenceType.custom, dt.date(2026, 1, 1), custom_interval_value=5
    )
    with pytest.raises(ValueError):
        generate_occurrences(series, dt.date(2026, 1, 1), dt.date(2026, 1, 31))


def test_series_end_date_clips_occurrences():
    series = make_series(
        CadenceType.weekly, dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 10)
    )
    dates = generate_occurrences(series, dt.date(2026, 1, 1), dt.date(2026, 2, 1))
    assert dates == [dt.date(2026, 1, 1), dt.date(2026, 1, 8)]


def test_series_start_date_after_range_start_is_respected():
    series = make_series(CadenceType.weekly, dt.date(2026, 1, 15))
    dates = generate_occurrences(series, dt.date(2026, 1, 1), dt.date(2026, 1, 31))
    assert dates == [dt.date(2026, 1, 15), dt.date(2026, 1, 22), dt.date(2026, 1, 29)]


def test_range_entirely_before_series_start_returns_empty():
    series = make_series(CadenceType.weekly, dt.date(2026, 6, 1))
    dates = generate_occurrences(series, dt.date(2026, 1, 1), dt.date(2026, 2, 1))
    assert dates == []


def test_range_entirely_after_series_end_returns_empty():
    series = make_series(
        CadenceType.weekly, dt.date(2026, 1, 1), end_date=dt.date(2026, 2, 1)
    )
    dates = generate_occurrences(series, dt.date(2026, 6, 1), dt.date(2026, 7, 1))
    assert dates == []


def test_inverted_range_returns_empty():
    series = make_series(CadenceType.weekly, dt.date(2026, 1, 1))
    dates = generate_occurrences(series, dt.date(2026, 2, 1), dt.date(2026, 1, 1))
    assert dates == []


def test_unsupported_cadence_type_raises():
    series = make_series("bogus", dt.date(2026, 1, 1))
    with pytest.raises(ValueError):
        generate_occurrences(series, dt.date(2026, 1, 1), dt.date(2026, 1, 31))


def make_amount_series(
    cadence_type,
    amount,
    custom_interval_value=None,
    custom_interval_unit=None,
):
    return SimpleNamespace(
        cadence_type=cadence_type,
        amount=Decimal(amount),
        custom_interval_value=custom_interval_value,
        custom_interval_unit=custom_interval_unit,
    )


def test_per_month_monthly_is_unchanged():
    series = make_amount_series(CadenceType.monthly, "100")
    assert per_month_amount(series) == Decimal("100")


def test_per_month_weekly():
    series = make_amount_series(CadenceType.weekly, "100")
    assert per_month_amount(series) == Decimal("100") * Decimal(52) / Decimal(12)


def test_per_month_biweekly():
    series = make_amount_series(CadenceType.biweekly, "100")
    assert per_month_amount(series) == Decimal("100") * Decimal(26) / Decimal(12)


def test_per_month_semi_monthly_doubles():
    series = make_amount_series(CadenceType.semi_monthly, "50")
    assert per_month_amount(series) == Decimal("100")


def test_per_month_quarterly():
    series = make_amount_series(CadenceType.quarterly, "300")
    assert per_month_amount(series) == Decimal("300") / 3


def test_per_month_yearly():
    series = make_amount_series(CadenceType.yearly, "1200")
    assert per_month_amount(series) == Decimal("1200") / 12


def test_per_month_custom_days():
    series = make_amount_series(
        CadenceType.custom, "10", custom_interval_value=2, custom_interval_unit=CustomIntervalUnit.days
    )
    assert per_month_amount(series) == Decimal("10") * (Decimal("30.44") / Decimal(2))


def test_per_month_custom_weeks():
    series = make_amount_series(
        CadenceType.custom, "10", custom_interval_value=3, custom_interval_unit=CustomIntervalUnit.weeks
    )
    assert per_month_amount(series) == Decimal("10") * (Decimal(52) / Decimal(12)) / Decimal(3)


def test_per_month_custom_months():
    series = make_amount_series(
        CadenceType.custom, "60", custom_interval_value=2, custom_interval_unit=CustomIntervalUnit.months
    )
    assert per_month_amount(series) == Decimal("60") / 2


def test_per_month_custom_without_unit_raises():
    series = make_amount_series(CadenceType.custom, "10", custom_interval_value=2)
    with pytest.raises(ValueError):
        per_month_amount(series)


def test_per_month_unsupported_cadence_raises():
    series = make_amount_series("bogus", "10")
    with pytest.raises(ValueError):
        per_month_amount(series)

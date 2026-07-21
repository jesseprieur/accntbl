import datetime as dt
from types import SimpleNamespace

from app.services.credit_card import statement_periods


def make_settings(statement_close_day, payment_due_offset_days=20):
    return SimpleNamespace(
        statement_close_day=statement_close_day,
        payment_due_offset_days=payment_due_offset_days,
    )


def test_periods_within_a_year_are_monthly_and_contiguous():
    settings = make_settings(statement_close_day=15)
    periods = statement_periods(settings, dt.date(2026, 1, 1), dt.date(2026, 4, 30))
    assert [p.close_date for p in periods] == [
        dt.date(2026, 1, 15),
        dt.date(2026, 2, 15),
        dt.date(2026, 3, 15),
        dt.date(2026, 4, 15),
    ]
    # Periods are contiguous: each start is the day after the previous close.
    for prev, curr in zip(periods, periods[1:]):
        assert curr.start == prev.close_date + dt.timedelta(days=1)


def test_first_period_start_is_day_after_previous_months_close():
    settings = make_settings(statement_close_day=15)
    periods = statement_periods(settings, dt.date(2026, 1, 1), dt.date(2026, 1, 31))
    assert len(periods) == 1
    assert periods[0].start == dt.date(2025, 12, 16)
    assert periods[0].close_date == dt.date(2026, 1, 15)
    assert periods[0].due_date == dt.date(2026, 2, 4)


def test_close_day_clamps_to_shorter_months():
    settings = make_settings(statement_close_day=31)
    periods = statement_periods(settings, dt.date(2026, 1, 1), dt.date(2026, 3, 31))
    assert [p.close_date for p in periods] == [
        dt.date(2026, 1, 31),
        dt.date(2026, 2, 28),
        dt.date(2026, 3, 31),
    ]


def test_due_date_is_close_date_plus_offset():
    settings = make_settings(statement_close_day=10, payment_due_offset_days=25)
    periods = statement_periods(settings, dt.date(2026, 5, 1), dt.date(2026, 5, 31))
    assert periods[0].due_date == dt.date(2026, 5, 10) + dt.timedelta(days=25)


def test_range_that_excludes_all_close_dates_returns_empty():
    settings = make_settings(statement_close_day=1)
    # Close dates are the 1st of each month; this range spans the 2nd-30th.
    periods = statement_periods(settings, dt.date(2026, 6, 2), dt.date(2026, 6, 30))
    assert periods == []


def test_inverted_range_returns_empty():
    settings = make_settings(statement_close_day=15)
    periods = statement_periods(settings, dt.date(2026, 2, 1), dt.date(2026, 1, 1))
    assert periods == []


def test_range_start_after_this_months_close_skips_to_next_month():
    settings = make_settings(statement_close_day=5)
    periods = statement_periods(settings, dt.date(2026, 3, 10), dt.date(2026, 4, 30))
    assert [p.close_date for p in periods] == [
        dt.date(2026, 4, 5),
    ]
    assert periods[0].start == dt.date(2026, 3, 6)

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

from app.models import OccurrenceStatus
from app.services.credit_card import payment_due_transactions, statement_periods


def make_settings(statement_close_day, payment_due_offset_days=20, name="Default Credit Card"):
    return SimpleNamespace(
        name=name,
        statement_close_day=statement_close_day,
        payment_due_offset_days=payment_due_offset_days,
    )


def make_transaction(date, credit_amount=None, occurrence_status=None):
    return SimpleNamespace(
        date=date, credit_amount=credit_amount, occurrence_status=occurrence_status
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


def test_payment_due_sums_credit_amounts_within_period():
    settings = make_settings(statement_close_day=15, payment_due_offset_days=20)
    transactions = [
        make_transaction(dt.date(2026, 1, 5), credit_amount=Decimal("50.00")),
        make_transaction(dt.date(2026, 1, 15), credit_amount=Decimal("25.00")),
        # Outside the period (falls in the next statement period).
        make_transaction(dt.date(2026, 1, 16), credit_amount=Decimal("999.00")),
        # A cash-only row should be ignored entirely.
        make_transaction(dt.date(2026, 1, 10), credit_amount=None),
    ]
    dues = payment_due_transactions(
        settings, transactions, dt.date(2026, 2, 1), dt.date(2026, 2, 28)
    )
    assert len(dues) == 1
    assert dues[0].date == dt.date(2026, 2, 4)
    assert dues[0].cash_amount == Decimal("75.00")
    assert dues[0].name == "Default Credit Card Payment"


def test_payment_due_excludes_skipped_transactions():
    settings = make_settings(statement_close_day=15, payment_due_offset_days=20)
    transactions = [
        make_transaction(dt.date(2026, 1, 5), credit_amount=Decimal("50.00")),
        make_transaction(
            dt.date(2026, 1, 10),
            credit_amount=Decimal("30.00"),
            occurrence_status=OccurrenceStatus.skipped,
        ),
    ]
    dues = payment_due_transactions(
        settings, transactions, dt.date(2026, 2, 1), dt.date(2026, 2, 28)
    )
    assert dues[0].cash_amount == Decimal("50.00")


def test_payment_due_is_zero_when_no_credit_transactions_in_period():
    settings = make_settings(statement_close_day=15, payment_due_offset_days=20)
    dues = payment_due_transactions(
        settings, [], dt.date(2026, 2, 1), dt.date(2026, 2, 28)
    )
    assert len(dues) == 1
    assert dues[0].cash_amount == Decimal("0")


def test_payment_due_filters_by_due_date_not_close_date():
    settings = make_settings(statement_close_day=15, payment_due_offset_days=20)
    # The period closing 2026-01-15 is due 2026-02-04, outside this range, so
    # it must not appear even though its close_date falls inside the range.
    # Only the prior period (closed 2025-12-15, due 2026-01-04) qualifies.
    dues = payment_due_transactions(
        settings, [], dt.date(2026, 1, 1), dt.date(2026, 1, 31)
    )
    assert [d.date for d in dues] == [dt.date(2026, 1, 4)]


def test_payment_due_multiple_periods_ordered_by_due_date():
    settings = make_settings(statement_close_day=15, payment_due_offset_days=10)
    transactions = [
        make_transaction(dt.date(2026, 1, 10), credit_amount=Decimal("10.00")),
        make_transaction(dt.date(2026, 2, 10), credit_amount=Decimal("20.00")),
    ]
    dues = payment_due_transactions(
        settings, transactions, dt.date(2026, 1, 1), dt.date(2026, 3, 1)
    )
    assert [d.date for d in dues] == [dt.date(2026, 1, 25), dt.date(2026, 2, 25)]
    assert [d.cash_amount for d in dues] == [Decimal("10.00"), Decimal("20.00")]

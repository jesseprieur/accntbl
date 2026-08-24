import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

from app.models import Kind
from app.services.statistics import WINDOW_MONTHS, compute_running_total_extremes


def make_account(starting_balance):
    return SimpleNamespace(starting_balance=Decimal(str(starting_balance)))


def make_transaction(name, date, cash_amount, occurrence_status=None):
    return SimpleNamespace(
        name=name,
        date=date,
        kind=Kind.cash,
        amount=cash_amount,
        occurrence_status=occurrence_status,
        credit_card_id=None,
    )


def test_windows_are_three_six_and_twelve_months():
    assert WINDOW_MONTHS == (3, 6, 12)


def test_min_and_max_found_within_each_window():
    today = dt.date(2026, 1, 1)
    accounts = [make_account(1000)]
    transactions = [
        # Deep dip early, within every window.
        make_transaction("big expense", dt.date(2026, 1, 5), Decimal("-1500")),
        # Recovery + new high, only within the 6/12 month windows.
        make_transaction("paycheck", dt.date(2026, 4, 10), Decimal("3000")),
    ]

    results = compute_running_total_extremes(accounts, transactions, [], today)
    by_months = {r.months: r for r in results}

    three_month = by_months[3]
    assert three_month.min_value == Decimal("-500")
    assert three_month.min_date == dt.date(2026, 1, 5)
    # The paycheck lands after this window closes, so the balance never
    # recovers within it: min and max tie at the same post-expense value.
    assert three_month.max_value == Decimal("-500")
    assert three_month.max_date == dt.date(2026, 1, 5)

    six_month = by_months[6]
    assert six_month.min_value == Decimal("-500")
    assert six_month.min_date == dt.date(2026, 1, 5)
    assert six_month.max_value == Decimal("2500")
    assert six_month.max_date == dt.date(2026, 4, 10)


def test_tie_on_extreme_value_resolves_to_earliest_date():
    today = dt.date(2026, 1, 1)
    accounts = [make_account(0)]
    transactions = [
        make_transaction("first", dt.date(2026, 1, 5), Decimal("-100")),
        make_transaction("up", dt.date(2026, 1, 6), Decimal("100")),
        # Running total returns to -100 later in the window: earlier date should win.
        make_transaction("down again", dt.date(2026, 1, 10), Decimal("-100")),
    ]

    results = compute_running_total_extremes(accounts, transactions, [], today)
    three_month = next(r for r in results if r.months == 3)

    assert three_month.min_value == Decimal("-100")
    assert three_month.min_date == dt.date(2026, 1, 5)


def test_extreme_date_is_never_before_today_even_with_prior_history():
    today = dt.date(2026, 1, 15)
    accounts = [make_account(1000)]
    transactions = [
        # Occurs before "today": its effect on the running total carries
        # forward, but Jan 1 itself must never be reported as the extreme's
        # date since it falls outside [today, window_end].
        make_transaction("old expense", dt.date(2026, 1, 1), Decimal("-5000")),
        make_transaction("small expense", dt.date(2026, 1, 20), Decimal("-100")),
    ]

    results = compute_running_total_extremes(accounts, transactions, [], today)
    three_month = next(r for r in results if r.months == 3)

    assert three_month.min_value == Decimal("-4100")
    assert three_month.min_date == dt.date(2026, 1, 20)
    assert three_month.min_date >= today


def test_window_end_is_exact_calendar_month_boundary():
    today = dt.date(2026, 1, 31)
    accounts = [make_account(0)]

    results = compute_running_total_extremes(accounts, [], [], today)
    by_months = {r.months: r for r in results}

    assert by_months[3].window_end == dt.date(2026, 4, 30)
    assert by_months[6].window_end == dt.date(2026, 7, 31)
    assert by_months[12].window_end == dt.date(2027, 1, 31)

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

from app.models import Kind, NeedsWantsSavings, OccurrenceStatus
from app.services.statistics import (
    WINDOW_MONTHS,
    compute_needs_wants_savings_breakdown,
    compute_running_total_extremes,
    compute_spend_by_category_breakdown,
    rolling_12_months,
)


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


def make_full_transaction(
    date,
    amount,
    kind=Kind.cash,
    needs_wants_savings=NeedsWantsSavings.need,
    category_id=None,
    occurrence_status=None,
):
    return SimpleNamespace(
        date=date,
        amount=Decimal(str(amount)),
        kind=kind,
        needs_wants_savings=needs_wants_savings,
        category_id=category_id,
        occurrence_status=occurrence_status,
    )


def make_category(id, name, icon=None):
    return SimpleNamespace(id=id, name=name, icon=icon)


def test_rolling_12_months_starts_at_today_month():
    today = dt.date(2026, 3, 15)
    months = rolling_12_months(today)

    assert len(months) == 12
    assert months[0] == dt.date(2026, 3, 1)
    assert months[-1] == dt.date(2027, 2, 1)


def test_needs_wants_savings_breakdown_cash_only():
    today = dt.date(2026, 1, 1)
    transactions = [
        make_full_transaction(dt.date(2026, 1, 5), 2000, needs_wants_savings=NeedsWantsSavings.need),
        make_full_transaction(dt.date(2026, 1, 6), -800, needs_wants_savings=NeedsWantsSavings.need),
        make_full_transaction(dt.date(2026, 1, 7), -300, needs_wants_savings=NeedsWantsSavings.want),
        make_full_transaction(dt.date(2026, 1, 8), -200, needs_wants_savings=NeedsWantsSavings.savings),
    ]

    breakdown = compute_needs_wants_savings_breakdown(transactions, today, dt.date(2026, 1, 1))

    assert breakdown.income == Decimal("2000")
    assert breakdown.needs == Decimal("800")
    assert breakdown.wants == Decimal("300")
    assert breakdown.savings == Decimal("200")
    assert breakdown.leftover == Decimal("700")
    assert breakdown.pct_income == Decimal("100")
    assert breakdown.pct_needs == Decimal("40")
    assert breakdown.pct_wants == Decimal("15")
    assert breakdown.pct_savings == Decimal("10")
    assert breakdown.pct_leftover == Decimal("35")


def test_needs_wants_savings_breakdown_includes_credit_kind():
    today = dt.date(2026, 1, 1)
    transactions = [
        make_full_transaction(dt.date(2026, 1, 5), 1000, kind=Kind.cash),
        make_full_transaction(
            dt.date(2026, 1, 6), -400, kind=Kind.credit, needs_wants_savings=NeedsWantsSavings.want
        ),
    ]

    breakdown = compute_needs_wants_savings_breakdown(transactions, today, dt.date(2026, 1, 1))

    assert breakdown.income == Decimal("1000")
    assert breakdown.wants == Decimal("400")
    assert breakdown.leftover == Decimal("600")


def test_needs_wants_savings_breakdown_excludes_skipped_and_other_months():
    today = dt.date(2026, 1, 1)
    transactions = [
        make_full_transaction(dt.date(2026, 1, 5), 500),
        make_full_transaction(
            dt.date(2026, 1, 6), -500, occurrence_status=OccurrenceStatus.skipped
        ),
        make_full_transaction(dt.date(2026, 2, 6), -500),
    ]

    breakdown = compute_needs_wants_savings_breakdown(transactions, today, dt.date(2026, 1, 1))

    assert breakdown.income == Decimal("500")
    assert breakdown.needs == Decimal("0")
    assert breakdown.leftover == Decimal("500")


def test_needs_wants_savings_breakdown_zero_income_percentages_are_none():
    today = dt.date(2026, 1, 1)
    transactions = [
        make_full_transaction(dt.date(2026, 1, 5), -100, needs_wants_savings=NeedsWantsSavings.need),
    ]

    breakdown = compute_needs_wants_savings_breakdown(transactions, today, dt.date(2026, 1, 1))

    assert breakdown.income == Decimal("0")
    assert breakdown.pct_income is None
    assert breakdown.pct_needs is None
    assert breakdown.pct_wants is None
    assert breakdown.pct_savings is None
    assert breakdown.pct_leftover is None


def test_needs_wants_savings_breakdown_average_uses_averaged_dollars():
    today = dt.date(2026, 1, 1)
    transactions = [
        make_full_transaction(dt.date(2026, 1, 5), 1000),
        make_full_transaction(dt.date(2026, 1, 6), -500, needs_wants_savings=NeedsWantsSavings.need),
        make_full_transaction(dt.date(2026, 2, 5), 3000),
        make_full_transaction(dt.date(2026, 2, 6), -300, needs_wants_savings=NeedsWantsSavings.need),
    ]

    breakdown = compute_needs_wants_savings_breakdown(transactions, today, month=None)

    # 12-month rolling window: only Jan/Feb have activity, the other 10
    # months contribute zero, so the mean divides by 12 throughout.
    assert breakdown.income == Decimal("4000") / 12
    assert breakdown.needs == Decimal("800") / 12
    assert breakdown.pct_income == Decimal("100")
    assert breakdown.pct_needs == (breakdown.needs / breakdown.income) * 100


def test_spend_by_category_sums_and_excludes_positive_amounts():
    today = dt.date(2026, 1, 1)
    categories = [
        make_category(1, "Groceries"),
        make_category(2, "Rent"),
        make_category(3, "Uncategorized"),
    ]
    transactions = [
        make_full_transaction(dt.date(2026, 1, 5), 5000, category_id=1),  # income, excluded
        make_full_transaction(dt.date(2026, 1, 6), -100, category_id=1),
        make_full_transaction(dt.date(2026, 1, 7), -50, category_id=1, kind=Kind.credit),
        make_full_transaction(dt.date(2026, 1, 8), -1000, category_id=2),
        make_full_transaction(dt.date(2026, 1, 9), -25, category_id=3),
    ]

    rows = compute_spend_by_category_breakdown(transactions, categories, today, dt.date(2026, 1, 1))
    by_id = {row.category_id: row for row in rows}

    assert by_id[1].value == Decimal("150")
    assert by_id[2].value == Decimal("1000")
    assert by_id[3].value == Decimal("25")
    assert by_id[3].name == "Uncategorized"
    total = Decimal("150") + Decimal("1000") + Decimal("25")
    assert by_id[2].pct == (Decimal("1000") / total) * 100
    # Sorted by descending value.
    assert [row.category_id for row in rows] == [2, 1, 3]


def test_spend_by_category_always_includes_categories_with_no_spend():
    today = dt.date(2026, 1, 1)
    categories = [make_category(1, "Groceries"), make_category(2, "Unused")]
    transactions = [make_full_transaction(dt.date(2026, 1, 6), -100, category_id=1)]

    rows = compute_spend_by_category_breakdown(transactions, categories, today, dt.date(2026, 1, 1))
    by_id = {row.category_id: row for row in rows}

    assert by_id[2].value == Decimal("0")
    assert by_id[2].pct == Decimal("0")


def test_spend_by_category_zero_total_spend_percentages_are_none():
    today = dt.date(2026, 1, 1)
    categories = [make_category(1, "Groceries")]
    transactions = [make_full_transaction(dt.date(2026, 1, 6), 500, category_id=1)]

    rows = compute_spend_by_category_breakdown(transactions, categories, today, dt.date(2026, 1, 1))

    assert all(row.pct is None for row in rows)


def test_spend_by_category_excludes_skipped_occurrences():
    today = dt.date(2026, 1, 1)
    categories = [make_category(1, "Groceries")]
    transactions = [
        make_full_transaction(
            dt.date(2026, 1, 6), -100, category_id=1, occurrence_status=OccurrenceStatus.skipped
        )
    ]

    rows = compute_spend_by_category_breakdown(transactions, categories, today, dt.date(2026, 1, 1))
    by_id = {row.category_id: row for row in rows}

    assert by_id[1].value == Decimal("0")


def test_spend_by_category_average_uses_averaged_dollars():
    today = dt.date(2026, 1, 1)
    categories = [make_category(1, "Groceries")]
    transactions = [
        make_full_transaction(dt.date(2026, 1, 6), -120, category_id=1),
        make_full_transaction(dt.date(2026, 2, 6), -240, category_id=1),
    ]

    rows = compute_spend_by_category_breakdown(transactions, categories, today, month=None)
    by_id = {row.category_id: row for row in rows}

    assert by_id[1].value == (Decimal("120") + Decimal("240")) / 12

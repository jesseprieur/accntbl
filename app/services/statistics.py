"""Statistics page calculations.

See specs.md's "Statistics page" section: for each of three forward-looking
windows (3/6/12 months), find the min and max cash running total (and the
date each occurs on) within `[today, today + window]`, reusing the existing
running-total calculator.

Also implements the Needs/Wants/Savings/Leftover and spend-by-category
breakdown tables (specs.md §§ "Needs/Wants/Savings/Leftover breakdown
(Statistics page)" and "Spend-by-category breakdown (Statistics page)").
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.models import Kind, NeedsWantsSavings, OccurrenceStatus
from app.services.dates import add_months, month_bounds, rolling_months
from app.services.formatting import format_money, format_pct
from app.services.running_total import compute_running_total

WINDOW_MONTHS = (3, 6, 12)
BREAKDOWN_MONTH_COUNT = 12


@dataclass(frozen=True)
class WindowExtremes:
    months: int
    window_end: date
    min_value: object
    min_date: date
    max_value: object
    max_date: date


def compute_running_total_extremes(
    checking_accounts,
    transactions,
    credit_cards,
    today,
    credit_due_overrides=None,
):
    """Return one `WindowExtremes` per window in `WINDOW_MONTHS`.

    Ties on the extreme value within a window resolve to the earliest
    occurring date, matching specs.md.
    """
    window_ends = [add_months(today, months) for months in WINDOW_MONTHS]
    range_start = min([t.date for t in transactions] + [today])

    ledger = compute_running_total(
        checking_accounts,
        transactions,
        credit_cards,
        range_start,
        window_ends[-1],
        credit_due_overrides=credit_due_overrides,
    )

    results = []
    for months, window_end in zip(WINDOW_MONTHS, window_ends):
        min_row = None
        max_row = None
        for row in ledger:
            if not (today <= row.date <= window_end):
                continue
            if min_row is None or row.running_total < min_row.running_total:
                min_row = row
            if max_row is None or row.running_total > max_row.running_total:
                max_row = row
        results.append(
            WindowExtremes(
                months=months,
                window_end=window_end,
                min_value=min_row.running_total if min_row else None,
                min_date=min_row.date if min_row else None,
                max_value=max_row.running_total if max_row else None,
                max_date=max_row.date if max_row else None,
            )
        )
    return results


def rolling_12_months(today):
    """Return the 12 first-of-month dates starting with `today`'s month."""
    return rolling_months(today, BREAKDOWN_MONTH_COUNT)


def month_options(months):
    options = [{"value": m.strftime("%Y-%m"), "label": m.strftime("%B %Y")} for m in months]
    options.append({"value": "average", "label": "Average"})
    return options


def parse_month_selection(value, months):
    if value == "average":
        return None
    for month in months:
        if value == month.strftime("%Y-%m"):
            return month
    return months[0]


def serialize_nws_breakdown(breakdown):
    return {
        "rows": [
            {"label": "Income", "value": format_money(breakdown.income), "pct": format_pct(breakdown.pct_income)},
            {"label": "Needs", "value": format_money(breakdown.needs), "pct": format_pct(breakdown.pct_needs)},
            {"label": "Wants", "value": format_money(breakdown.wants), "pct": format_pct(breakdown.pct_wants)},
            {"label": "Savings", "value": format_money(breakdown.savings), "pct": format_pct(breakdown.pct_savings)},
            {"label": "Leftover", "value": format_money(breakdown.leftover), "pct": format_pct(breakdown.pct_leftover)},
        ]
    }


def serialize_category_rows(rows):
    return {
        "rows": [
            {
                "category_id": row.category_id,
                "name": row.name,
                "icon": row.icon,
                "value": format_money(row.value),
                "pct": format_pct(row.pct),
            }
            for row in rows
        ]
    }


def _in_breakdown_scope(transaction, month_start, month_end):
    """Both breakdown tables share this scope: real cash/credit transactions

    dated within the month, excluding skipped occurrences. Generated CC
    payment-due rows and month-end virtual rows are never included since
    they aren't `Transaction` rows at all.
    """
    return (
        transaction.kind in (Kind.cash, Kind.credit)
        and transaction.occurrence_status != OccurrenceStatus.skipped
        and month_start <= transaction.date <= month_end
    )


@dataclass(frozen=True)
class NeedsWantsSavingsBreakdown:
    income: Decimal
    needs: Decimal
    wants: Decimal
    savings: Decimal
    leftover: Decimal
    pct_income: Decimal
    pct_needs: Decimal
    pct_wants: Decimal
    pct_savings: Decimal
    pct_leftover: Decimal


def _nws_dollars_for_month(transactions, month_start, month_end):
    income = needs = wants = savings = Decimal("0")
    for t in transactions:
        if not _in_breakdown_scope(t, month_start, month_end):
            continue
        if t.amount > 0:
            income += t.amount
        else:
            magnitude = -t.amount
            if t.needs_wants_savings == NeedsWantsSavings.need:
                needs += magnitude
            elif t.needs_wants_savings == NeedsWantsSavings.want:
                wants += magnitude
            elif t.needs_wants_savings == NeedsWantsSavings.savings:
                savings += magnitude
    return income, needs, wants, savings


def _nws_breakdown_from_dollars(income, needs, wants, savings):
    leftover = income - (needs + wants + savings)
    if income == 0:
        pct_income = pct_needs = pct_wants = pct_savings = pct_leftover = None
    else:
        pct_income = Decimal("100")
        pct_needs = (needs / income) * 100
        pct_wants = (wants / income) * 100
        pct_savings = (savings / income) * 100
        pct_leftover = (leftover / income) * 100
    return NeedsWantsSavingsBreakdown(
        income=income,
        needs=needs,
        wants=wants,
        savings=savings,
        leftover=leftover,
        pct_income=pct_income,
        pct_needs=pct_needs,
        pct_wants=pct_wants,
        pct_savings=pct_savings,
        pct_leftover=pct_leftover,
    )


def compute_needs_wants_savings_breakdown(transactions, today, month=None):
    """Compute the Income/Needs/Wants/Savings/Leftover breakdown.

    `month` is a first-of-month `date` from `rolling_12_months(today)`, or
    `None` to compute the "Average" option (mean dollar value per bucket
    across the rolling 12-month window, with `%` derived from those averaged
    dollars — see specs.md).
    """
    if month is None:
        months = rolling_12_months(today)
        totals = [Decimal("0")] * 4
        for month_start in months:
            month_end = month_bounds(month_start)[1]
            dollars = _nws_dollars_for_month(transactions, month_start, month_end)
            totals = [total + value for total, value in zip(totals, dollars)]
        income, needs, wants, savings = (total / len(months) for total in totals)
    else:
        month_start, month_end = month_bounds(month)
        income, needs, wants, savings = _nws_dollars_for_month(
            transactions, month_start, month_end
        )
    return _nws_breakdown_from_dollars(income, needs, wants, savings)


@dataclass(frozen=True)
class CategorySpendRow:
    category_id: int
    name: str
    icon: str
    value: Decimal
    pct: Decimal


def _spend_by_category_for_month(transactions, month_start, month_end):
    sums = defaultdict(lambda: Decimal("0"))
    for t in transactions:
        if not _in_breakdown_scope(t, month_start, month_end):
            continue
        if t.amount >= 0:
            continue
        sums[t.category_id] += -t.amount
    return sums


def compute_spend_by_category_breakdown(transactions, categories, today, month=None):
    """Compute the per-category spend breakdown.

    `month` is a first-of-month `date` from `rolling_12_months(today)`, or
    `None` for the "Average" option (mean dollar value per category across
    the rolling 12-month window). Returns one `CategorySpendRow` per
    category (every transaction's `category_id` is non-nullable, so
    `categories` already includes `Uncategorized` — no separate bucket is
    needed), sorted by descending value.
    """
    if month is None:
        months = rolling_12_months(today)
        combined = defaultdict(lambda: Decimal("0"))
        for month_start in months:
            month_end = month_bounds(month_start)[1]
            for category_id, value in _spend_by_category_for_month(
                transactions, month_start, month_end
            ).items():
                combined[category_id] += value
        sums = {
            category_id: value / len(months) for category_id, value in combined.items()
        }
    else:
        month_start, month_end = month_bounds(month)
        sums = _spend_by_category_for_month(transactions, month_start, month_end)

    total = sum(sums.values(), Decimal("0"))

    def pct(value):
        return (value / total) * 100 if total > 0 else None

    rows = [
        CategorySpendRow(
            category_id=category.id,
            name=category.name,
            icon=category.icon,
            value=sums.get(category.id, Decimal("0")),
            pct=pct(sums.get(category.id, Decimal("0"))),
        )
        for category in categories
    ]
    rows.sort(key=lambda row: row.value, reverse=True)
    return rows

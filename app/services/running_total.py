"""Running checking-balance total calculator.

Combines real `transactions` rows with the virtual credit-card payment-due
rows from `app.services.credit_card.payment_due_transactions` into a single
ascending-by-date ledger, and walks it to produce a running total. See
specs.md's "Running total calculation" section.
"""
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.models import OccurrenceStatus
from app.services.credit_card import payment_due_transactions


@dataclass(frozen=True)
class LedgerRow:
    name: str
    date: date
    cash_amount: Decimal
    running_total: Decimal
    is_negative: bool
    transaction: object = None
    is_month_end: bool = False
    month_over_month_change: Decimal = None


def _month_end_dates(range_start, range_end):
    """Last-calendar-day dates for every month overlapping [range_start, range_end]."""
    dates = []
    year, month = range_start.year, range_start.month
    while True:
        last_day = monthrange(year, month)[1]
        month_end = date(year, month, last_day)
        if month_end > range_end:
            break
        dates.append(month_end)
        month += 1
        if month > 12:
            month = 1
            year += 1
    return dates


def compute_running_total(
    checking_accounts,
    transactions,
    credit_card_settings,
    range_start,
    range_end,
    include_month_end=True,
):
    """Return `LedgerRow`s in ascending date order with a running total.

    `transactions` should include all real rows relevant to the running
    total (skipped occurrences are filtered out here). Virtual credit-card
    payment-due rows are generated on the fly for statement periods whose
    due_date falls within [range_start, range_end] and merged in; ties on the
    same date keep real rows ahead of the virtual payment-due row. A virtual
    "month end" marker row is also merged in for every month overlapping the
    range, sorted after any same-date rows so it reflects the balance as of
    the close of that day.
    """
    baseline = sum((a.starting_balance for a in checking_accounts), Decimal("0"))

    real_rows = [
        (t.date, t.name, t.cash_amount or Decimal("0"), t, False)
        for t in transactions
        if t.occurrence_status != OccurrenceStatus.skipped
    ]

    virtual_rows = []
    if credit_card_settings is not None:
        dues = payment_due_transactions(
            credit_card_settings, transactions, range_start, range_end
        )
        virtual_rows = [(d.date, d.name, d.cash_amount, None, False) for d in dues]

    month_end_rows = (
        [
            (month_end, "Month end", Decimal("0"), None, True)
            for month_end in _month_end_dates(range_start, range_end)
        ]
        if include_month_end
        else []
    )

    all_rows = sorted(
        real_rows + virtual_rows + month_end_rows,
        key=lambda row: (row[0], row[4]),
    )

    running_total = baseline
    previous_month_end_total = None
    results = []
    for row_date, name, cash_amount, transaction, is_month_end in all_rows:
        running_total += cash_amount
        month_over_month_change = None
        if is_month_end:
            if previous_month_end_total is not None:
                month_over_month_change = running_total - previous_month_end_total
            previous_month_end_total = running_total
        results.append(
            LedgerRow(
                name=name,
                date=row_date,
                cash_amount=cash_amount,
                running_total=running_total,
                is_negative=running_total < 0,
                transaction=transaction,
                is_month_end=is_month_end,
                month_over_month_change=month_over_month_change,
            )
        )
    return results

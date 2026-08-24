"""Statistics page calculations.

See specs.md's "Statistics page" section: for each of three forward-looking
windows (3/6/12 months), find the min and max cash running total (and the
date each occurs on) within `[today, today + window]`, reusing the existing
running-total calculator.
"""
import calendar
from dataclasses import dataclass
from datetime import date

from app.services.running_total import compute_running_total

WINDOW_MONTHS = (3, 6, 12)


def _add_months(d, months):
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


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
    window_ends = [_add_months(today, months) for months in WINDOW_MONTHS]
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

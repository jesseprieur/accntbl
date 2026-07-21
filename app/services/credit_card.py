"""Credit card statement period calculator.

Given a `CreditCardSettings` row and a date range, compute the sequence of
monthly statement periods (start, close_date, due_date) whose close_date
falls within the range. See specs.md's "Credit card payment logic" section.
"""
import calendar
from dataclasses import dataclass
from datetime import date, timedelta

# Safety cap on loop iterations so malformed settings can't hang the request.
_MAX_ITERATIONS = 10_000


@dataclass(frozen=True)
class StatementPeriod:
    start: date
    close_date: date
    due_date: date


def _close_date_for_month_offset(anchor_year, anchor_month, offset, statement_close_day):
    month_index = anchor_month - 1 + offset
    year = anchor_year + month_index // 12
    month = month_index % 12 + 1
    day = min(statement_close_day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def statement_periods(settings, range_start, range_end):
    """Return the list of statement periods whose `close_date` falls within
    [range_start, range_end], ordered ascending by close_date.

    Each period's `start` is the day after the previous period's
    `close_date`, so periods are contiguous and non-overlapping regardless
    of month length/clamping.
    """
    if range_start > range_end:
        return []

    statement_close_day = settings.statement_close_day
    payment_due_offset_days = settings.payment_due_offset_days

    periods = []
    # Start one month before range_start so the first in-range period gets
    # the correct `start` boundary (day after the true previous close).
    prev_close = _close_date_for_month_offset(
        range_start.year, range_start.month, -1, statement_close_day
    )

    k = 0
    iterations = 0
    while True:
        close_date = _close_date_for_month_offset(
            range_start.year, range_start.month, k, statement_close_day
        )
        if close_date > range_end:
            break
        if close_date >= range_start:
            periods.append(
                StatementPeriod(
                    start=prev_close + timedelta(days=1),
                    close_date=close_date,
                    due_date=close_date + timedelta(days=payment_due_offset_days),
                )
            )
        prev_close = close_date
        k += 1
        iterations += 1
        if iterations > _MAX_ITERATIONS:
            break

    return periods

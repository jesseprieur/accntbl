"""Shared month/interval arithmetic.

The one implementation of calendar math used by every feature that needs
it (recurring occurrence generation, running-total windows, statistics
breakdowns) — see specs.md § "Application structure".
"""
import calendar
from datetime import date


def add_months(d, months):
    """Return `d` shifted forward by `months` calendar months, clamping the
    day to the last day of the target month if it doesn't exist there
    (e.g. Jan 31 + 1 month -> Feb 28)."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


def month_bounds(month_start):
    """Return `(month_start, month_end)` for the calendar month containing
    `month_start` (which must already be the first of its month)."""
    last_day = calendar.monthrange(month_start.year, month_start.month)[1]
    return month_start, month_start.replace(day=last_day)


def rolling_months(start, count):
    """Return `count` first-of-month dates starting with `start`'s month."""
    first_of_month = start.replace(day=1)
    return [add_months(first_of_month, i) for i in range(count)]


def month_end_dates(range_start, range_end):
    """Last-calendar-day dates for every month overlapping [range_start, range_end]."""
    dates = []
    year, month = range_start.year, range_start.month
    while True:
        last_day = calendar.monthrange(year, month)[1]
        month_end = date(year, month, last_day)
        if month_end > range_end:
            break
        dates.append(month_end)
        month += 1
        if month > 12:
            month = 1
            year += 1
    return dates

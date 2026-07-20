"""Recurring occurrence generator.

Given a `RecurringSeries` and a date range, produce the concrete dates on
which that series occurs within the range. See specs.md's
`recurring_series` section for the cadence/interval semantics.
"""
import calendar
from datetime import timedelta

from app.models import CadenceType, CustomIntervalUnit

_DAY_INTERVALS = {
    CadenceType.weekly: 7,
    CadenceType.biweekly: 14,
}

_MONTH_INTERVALS = {
    CadenceType.monthly: 1,
    CadenceType.quarterly: 3,
    CadenceType.yearly: 12,
}

# Safety cap on loop iterations so a malformed series can't hang the request.
_MAX_ITERATIONS = 1_000


def _add_months(d, months):
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


def _effective_end(series, range_end):
    if series.end_date is not None and series.end_date < range_end:
        return series.end_date
    return range_end


def _generate_day_based(series, interval_days, range_start, range_end):
    dates = []
    end = _effective_end(series, range_end)
    if series.start_date > end:
        return dates

    candidate = series.start_date
    if range_start > candidate:
        elapsed = (range_start - candidate).days
        candidate += timedelta(days=(elapsed // interval_days) * interval_days)
        while candidate < range_start:
            candidate += timedelta(days=interval_days)

    iterations = 0
    while candidate <= end:
        if candidate >= range_start:
            dates.append(candidate)
        candidate += timedelta(days=interval_days)
        iterations += 1
        if iterations > _MAX_ITERATIONS:
            break
    return dates


def _generate_month_based(series, interval_months, range_start, range_end):
    dates = []
    end = _effective_end(series, range_end)
    if series.start_date > end:
        return dates

    k = 0
    while True:
        candidate = _add_months(series.start_date, k * interval_months)
        if candidate > end:
            break
        if candidate >= range_start:
            dates.append(candidate)
        k += 1
        if k > _MAX_ITERATIONS:
            break
    return dates


def _generate_semi_monthly(series, range_start, range_end):
    dates = []
    end = _effective_end(series, range_end)
    if series.start_date > end:
        return dates

    k = 0
    while True:
        month_anchor = _add_months(series.start_date, k)
        if month_anchor > end:
            break
        last_day = calendar.monthrange(month_anchor.year, month_anchor.month)[1]
        second = month_anchor.replace(day=min(series.start_date.day + 15, last_day))

        for candidate in (month_anchor, second):
            if series.start_date <= candidate <= end and candidate >= range_start:
                dates.append(candidate)

        k += 1
        if k > _MAX_ITERATIONS:
            break
    return sorted(set(dates))


def generate_occurrences(series, range_start, range_end):
    """Return the sorted list of occurrence dates for `series` that fall
    within [range_start, range_end], clipped to the series' own
    start_date/end_date.
    """
    if range_start > range_end:
        return []

    cadence = series.cadence_type

    if cadence in _DAY_INTERVALS:
        return _generate_day_based(
            series, _DAY_INTERVALS[cadence], range_start, range_end
        )

    if cadence in _MONTH_INTERVALS:
        return _generate_month_based(
            series, _MONTH_INTERVALS[cadence], range_start, range_end
        )

    if cadence == CadenceType.semi_monthly:
        return _generate_semi_monthly(series, range_start, range_end)

    if cadence == CadenceType.custom:
        if series.custom_interval_unit == CustomIntervalUnit.days:
            return _generate_day_based(
                series, series.custom_interval_value, range_start, range_end
            )
        if series.custom_interval_unit == CustomIntervalUnit.weeks:
            return _generate_day_based(
                series, series.custom_interval_value * 7, range_start, range_end
            )
        if series.custom_interval_unit == CustomIntervalUnit.months:
            return _generate_month_based(
                series, series.custom_interval_value, range_start, range_end
            )
        raise ValueError("custom cadence requires custom_interval_unit")

    raise ValueError(f"unsupported cadence_type: {cadence!r}")

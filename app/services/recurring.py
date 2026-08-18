"""Recurring occurrence generator.

Given a `RecurringSeries` and a date range, produce the concrete dates on
which that series occurs within the range. See specs.md's
`recurring_series` section for the cadence/interval semantics.
"""
import calendar
from datetime import timedelta
from decimal import Decimal

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
        month_anchor = _add_months(series.start_date.replace(day=1), k)
        if month_anchor > end:
            break
        last_day = calendar.monthrange(month_anchor.year, month_anchor.month)[1]
        mid = month_anchor.replace(day=15)
        eom = month_anchor.replace(day=last_day)

        for candidate in (mid, eom):
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


_MONTHLY_MULTIPLIERS = {
    CadenceType.monthly: Decimal(1),
    CadenceType.weekly: Decimal(52) / Decimal(12),
    CadenceType.biweekly: Decimal(26) / Decimal(12),
    CadenceType.semi_monthly: Decimal(2),
}

_MONTHLY_DIVISORS = {
    CadenceType.quarterly: Decimal(3),
    CadenceType.yearly: Decimal(12),
}

_AVERAGE_DAYS_PER_MONTH = Decimal("30.44")


def per_month_amount(series):
    """Normalize `series.amount` to an average monthly rate, per
    specs.md's "Per Month column (Recurring Series page)" section. Always
    uses the plain `amount` field, even when `amount_logic` is set.
    """
    cadence = series.cadence_type
    amount = Decimal(series.amount)

    if cadence in _MONTHLY_MULTIPLIERS:
        return amount * _MONTHLY_MULTIPLIERS[cadence]

    if cadence in _MONTHLY_DIVISORS:
        return amount / _MONTHLY_DIVISORS[cadence]

    if cadence == CadenceType.custom:
        interval_value = Decimal(series.custom_interval_value)
        unit = series.custom_interval_unit
        if unit == CustomIntervalUnit.days:
            return amount * (_AVERAGE_DAYS_PER_MONTH / interval_value)
        if unit == CustomIntervalUnit.weeks:
            return amount * (Decimal(52) / Decimal(12)) / interval_value
        if unit == CustomIntervalUnit.months:
            return amount / interval_value
        raise ValueError("custom cadence requires custom_interval_unit")

    raise ValueError(f"unsupported cadence_type: {cadence!r}")

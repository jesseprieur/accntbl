"""Shared money/percent formatting for server-rendered and JSON responses.

The one implementation used by every route/service that serializes a
dollar amount or a `%` — see specs.md § "Application structure".
"""


def format_money(value):
    return "${:,.2f}".format(value)


def format_pct(value):
    return "—" if value is None else "{:.1f}%".format(value)

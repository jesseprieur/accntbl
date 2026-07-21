"""Running checking-balance total calculator.

Combines real `transactions` rows with the virtual credit-card payment-due
rows from `app.services.credit_card.payment_due_transactions` into a single
ascending-by-date ledger, and walks it to produce a running total. See
specs.md's "Running total calculation" section.
"""
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


def compute_running_total(
    checking_accounts, transactions, credit_card_settings, range_start, range_end
):
    """Return `LedgerRow`s in ascending date order with a running total.

    `transactions` should include all real rows relevant to the running
    total (skipped occurrences are filtered out here). Virtual credit-card
    payment-due rows are generated on the fly for statement periods whose
    due_date falls within [range_start, range_end] and merged in; ties on the
    same date keep real rows ahead of the virtual payment-due row.
    """
    baseline = sum((a.starting_balance for a in checking_accounts), Decimal("0"))

    real_rows = [
        (t.date, t.name, t.cash_amount or Decimal("0"), t)
        for t in transactions
        if t.occurrence_status != OccurrenceStatus.skipped
    ]

    virtual_rows = []
    if credit_card_settings is not None:
        dues = payment_due_transactions(
            credit_card_settings, transactions, range_start, range_end
        )
        virtual_rows = [(d.date, d.name, -d.cash_amount, None) for d in dues]

    all_rows = sorted(real_rows + virtual_rows, key=lambda row: row[0])

    running_total = baseline
    results = []
    for row_date, name, cash_amount, transaction in all_rows:
        running_total += cash_amount
        results.append(
            LedgerRow(
                name=name,
                date=row_date,
                cash_amount=cash_amount,
                running_total=running_total,
                is_negative=running_total < 0,
                transaction=transaction,
            )
        )
    return results

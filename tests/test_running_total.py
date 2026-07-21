import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

from app.models import OccurrenceStatus
from app.services.running_total import compute_running_total


def make_account(starting_balance):
    return SimpleNamespace(starting_balance=Decimal(str(starting_balance)))


def make_settings(statement_close_day, payment_due_offset_days=20, name="Default Credit Card"):
    return SimpleNamespace(
        name=name,
        statement_close_day=statement_close_day,
        payment_due_offset_days=payment_due_offset_days,
    )


def make_transaction(
    name, date, cash_amount=None, credit_amount=None, occurrence_status=None
):
    return SimpleNamespace(
        name=name,
        date=date,
        cash_amount=cash_amount,
        credit_amount=credit_amount,
        occurrence_status=occurrence_status,
    )


def test_baseline_is_sum_of_all_checking_accounts():
    accounts = [make_account(1000), make_account(500)]
    rows = compute_running_total(
        accounts, [], None, dt.date(2026, 1, 1), dt.date(2026, 1, 31)
    )
    assert rows == []


def test_walks_transactions_ascending_and_accumulates_cash_amount():
    accounts = [make_account(100)]
    transactions = [
        make_transaction("paycheck", dt.date(2026, 1, 15), cash_amount=Decimal("200")),
        make_transaction("rent", dt.date(2026, 1, 1), cash_amount=Decimal("-50")),
    ]
    rows = compute_running_total(
        accounts, transactions, None, dt.date(2026, 1, 1), dt.date(2026, 1, 31)
    )
    assert [r.name for r in rows] == ["rent", "paycheck"]
    assert [r.running_total for r in rows] == [Decimal("50"), Decimal("250")]


def test_credit_amount_does_not_affect_running_total():
    accounts = [make_account(100)]
    transactions = [
        make_transaction("groceries", dt.date(2026, 1, 5), credit_amount=Decimal("40")),
    ]
    rows = compute_running_total(
        accounts, transactions, None, dt.date(2026, 1, 1), dt.date(2026, 1, 31)
    )
    assert len(rows) == 1
    assert rows[0].cash_amount == Decimal("0")
    assert rows[0].running_total == Decimal("100")


def test_skipped_transactions_are_excluded():
    accounts = [make_account(100)]
    transactions = [
        make_transaction(
            "skipped rent",
            dt.date(2026, 1, 1),
            cash_amount=Decimal("-50"),
            occurrence_status=OccurrenceStatus.skipped,
        ),
        make_transaction("paycheck", dt.date(2026, 1, 15), cash_amount=Decimal("200")),
    ]
    rows = compute_running_total(
        accounts, transactions, None, dt.date(2026, 1, 1), dt.date(2026, 1, 31)
    )
    assert [r.name for r in rows] == ["paycheck"]
    assert rows[0].running_total == Decimal("300")


def test_negative_running_total_is_flagged():
    accounts = [make_account(100)]
    transactions = [
        make_transaction("big expense", dt.date(2026, 1, 5), cash_amount=Decimal("-150")),
        make_transaction("paycheck", dt.date(2026, 1, 15), cash_amount=Decimal("200")),
    ]
    rows = compute_running_total(
        accounts, transactions, None, dt.date(2026, 1, 1), dt.date(2026, 1, 31)
    )
    assert rows[0].running_total == Decimal("-50")
    assert rows[0].is_negative is True
    assert rows[1].running_total == Decimal("150")
    assert rows[1].is_negative is False


def test_credit_card_payment_due_row_is_merged_into_ledger():
    accounts = [make_account(1000)]
    settings = make_settings(statement_close_day=15, payment_due_offset_days=20)
    transactions = [
        make_transaction(
            "coffee", dt.date(2026, 1, 5), credit_amount=Decimal("50")
        ),
        make_transaction(
            "paycheck", dt.date(2026, 2, 1), cash_amount=Decimal("300")
        ),
    ]
    rows = compute_running_total(
        accounts, transactions, settings, dt.date(2026, 2, 1), dt.date(2026, 2, 28)
    )
    # `coffee` is a credit-only transaction, so it still appears in the
    # ledger as its own row (cash_amount 0, no effect on the total), while
    # also feeding the CC payment-due amount for the period it falls in.
    assert [r.name for r in rows] == [
        "coffee",
        "paycheck",
        "Default Credit Card Payment",
    ]
    assert rows[2].date == dt.date(2026, 2, 4)
    assert rows[2].cash_amount == Decimal("-50")
    assert rows[2].running_total == Decimal("1250")


def test_real_row_ordered_before_virtual_row_on_same_date():
    accounts = [make_account(0)]
    settings = make_settings(statement_close_day=15, payment_due_offset_days=20)
    transactions = [
        make_transaction(
            "same day cash", dt.date(2026, 2, 4), cash_amount=Decimal("10")
        ),
    ]
    rows = compute_running_total(
        accounts, transactions, settings, dt.date(2026, 2, 1), dt.date(2026, 2, 28)
    )
    assert [r.name for r in rows] == ["same day cash", "Default Credit Card Payment"]

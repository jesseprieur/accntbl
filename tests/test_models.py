import datetime

import pytest

from app import create_app
from app.extensions import db
import sqlalchemy.exc

from app.models import (
    CadenceType,
    CheckingAccount,
    CreditCard,
    CreditDueOverride,
    Kind,
    OccurrenceStatus,
    RecurringSeries,
    Transaction,
    User,
)


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_user_roundtrip(app):
    db.session.add(User(username="anita", password_hash="hashed"))
    db.session.commit()

    user = User.query.filter_by(username="anita").one()
    assert user.password_hash == "hashed"


def test_checking_account_roundtrip(app):
    db.session.add(
        CheckingAccount(
            name="Primary Checking",
            starting_balance="1000.50",
            as_of_date=datetime.date(2026, 7, 19),
        )
    )
    db.session.commit()

    account = CheckingAccount.query.one()
    assert account.starting_balance == 1000.50
    assert account.as_of_date == datetime.date(2026, 7, 19)


def test_credit_card_settings_roundtrip(app):
    db.session.add(
        CreditCard(
            name="Default Credit Card",
            statement_close_day=15,
            payment_due_offset_days=21,
            starting_balance="250.00",
        )
    )
    db.session.commit()

    settings = CreditCard.query.one()
    assert settings.statement_close_day == 15
    assert settings.payment_due_offset_days == 21


def test_credit_card_set_default_unsets_other_cards(app):
    first = CreditCard(
        name="First Card",
        is_default=True,
        statement_close_day=1,
        payment_due_offset_days=10,
    )
    second = CreditCard(
        name="Second Card",
        is_default=False,
        statement_close_day=15,
        payment_due_offset_days=20,
    )
    db.session.add_all([first, second])
    db.session.commit()

    CreditCard.set_default(second)
    db.session.commit()

    db.session.refresh(first)
    assert first.is_default is False
    assert second.is_default is True
    assert CreditCard.query.filter_by(is_default=True).count() == 1


def test_deletion_blocker_none_when_second_non_default_card_is_unreferenced(app):
    first = CreditCard(
        name="First Card",
        is_default=True,
        statement_close_day=1,
        payment_due_offset_days=10,
    )
    second = CreditCard(
        name="Second Card",
        is_default=False,
        statement_close_day=15,
        payment_due_offset_days=20,
    )
    db.session.add_all([first, second])
    db.session.commit()

    assert second.deletion_blocker() is None


def test_deletion_blocker_blocks_last_remaining_card(app):
    only_card = CreditCard(
        name="Only Card",
        is_default=True,
        statement_close_day=1,
        payment_due_offset_days=10,
    )
    db.session.add(only_card)
    db.session.commit()

    assert only_card.deletion_blocker() is not None


def test_deletion_blocker_blocks_default_card_when_others_exist(app):
    first = CreditCard(
        name="First Card",
        is_default=True,
        statement_close_day=1,
        payment_due_offset_days=10,
    )
    second = CreditCard(
        name="Second Card",
        is_default=False,
        statement_close_day=15,
        payment_due_offset_days=20,
    )
    db.session.add_all([first, second])
    db.session.commit()

    assert first.deletion_blocker() is not None


def test_deletion_blocker_blocks_card_referenced_by_transaction(app):
    first = CreditCard(
        name="First Card",
        is_default=True,
        statement_close_day=1,
        payment_due_offset_days=10,
    )
    second = CreditCard(
        name="Second Card",
        is_default=False,
        statement_close_day=15,
        payment_due_offset_days=20,
    )
    db.session.add_all([first, second])
    db.session.flush()

    db.session.add(
        Transaction(
            name="Groceries",
            kind=Kind.credit,
            amount="-50.00",
            date=datetime.date(2026, 1, 5),
            credit_card_id=second.id,
        )
    )
    db.session.commit()

    assert second.deletion_blocker() is not None


def test_deletion_blocker_blocks_card_referenced_by_recurring_series(app):
    first = CreditCard(
        name="First Card",
        is_default=True,
        statement_close_day=1,
        payment_due_offset_days=10,
    )
    second = CreditCard(
        name="Second Card",
        is_default=False,
        statement_close_day=15,
        payment_due_offset_days=20,
    )
    db.session.add_all([first, second])
    db.session.flush()

    db.session.add(
        RecurringSeries(
            name="Subscription",
            kind=Kind.credit,
            amount="-9.99",
            cadence_type=CadenceType.monthly,
            start_date=datetime.date(2026, 1, 1),
            credit_card_id=second.id,
        )
    )
    db.session.commit()

    assert second.deletion_blocker() is not None


def test_recurring_series_generated_transaction_is_linked_and_attached(app):
    series = RecurringSeries(
        name="Paycheck",
        kind=Kind.cash,
        amount="2000.00",
        cadence_type=CadenceType.biweekly,
        start_date=datetime.date(2026, 1, 1),
    )
    db.session.add(series)
    db.session.flush()

    occurrence = Transaction(
        name="Paycheck",
        kind=Kind.cash,
        amount="2000.00",
        date=datetime.date(2026, 1, 15),
        recurring_series_id=series.id,
        occurrence_status=OccurrenceStatus.attached,
    )
    db.session.add(occurrence)
    db.session.commit()

    fetched = Transaction.query.one()
    assert fetched.recurring_series.name == "Paycheck"
    assert fetched.occurrence_status == OccurrenceStatus.attached
    assert series.transactions == [fetched]


def test_one_off_transaction_has_no_series(app):
    db.session.add(
        Transaction(
            name="Groceries",
            kind=Kind.cash,
            amount="-75.25",
            date=datetime.date(2026, 7, 19),
        )
    )
    db.session.commit()

    transaction = Transaction.query.one()
    assert transaction.recurring_series_id is None
    assert transaction.occurrence_status is None


def test_cash_transaction_and_series_have_no_credit_card_by_default(app):
    db.session.add(
        Transaction(
            name="Groceries",
            kind=Kind.cash,
            amount="-75.25",
            date=datetime.date(2026, 7, 19),
        )
    )
    db.session.add(
        RecurringSeries(
            name="Paycheck",
            kind=Kind.cash,
            amount="2000.00",
            cadence_type=CadenceType.biweekly,
            start_date=datetime.date(2026, 1, 1),
        )
    )
    db.session.commit()

    assert Transaction.query.one().credit_card_id is None
    assert RecurringSeries.query.one().credit_card_id is None


def test_credit_transaction_and_series_link_to_credit_card(app):
    card = CreditCard(
        name="Amex Business",
        is_default=True,
        statement_close_day=10,
        payment_due_offset_days=20,
    )
    db.session.add(card)
    db.session.flush()

    transaction = Transaction(
        name="Office supplies",
        kind=Kind.credit,
        amount="-50.00",
        date=datetime.date(2026, 7, 19),
        credit_card_id=card.id,
    )
    series = RecurringSeries(
        name="Subscription",
        kind=Kind.credit,
        amount="-9.99",
        cadence_type=CadenceType.monthly,
        start_date=datetime.date(2026, 1, 1),
        credit_card_id=card.id,
    )
    db.session.add_all([transaction, series])
    db.session.commit()

    fetched_transaction = Transaction.query.filter_by(name="Office supplies").one()
    fetched_series = RecurringSeries.query.filter_by(name="Subscription").one()
    assert fetched_transaction.credit_card.name == "Amex Business"
    assert fetched_series.credit_card.name == "Amex Business"


def test_credit_due_override_roundtrip(app):
    card = CreditCard(
        name="Amex Business",
        is_default=True,
        statement_close_day=10,
        payment_due_offset_days=20,
    )
    db.session.add(card)
    db.session.flush()

    override = CreditDueOverride(
        credit_card_id=card.id,
        due_date=datetime.date(2026, 2, 9),
        amount="-475.50",
        notes="Included annual fee",
    )
    db.session.add(override)
    db.session.commit()

    fetched = CreditDueOverride.query.one()
    assert fetched.credit_card.name == "Amex Business"
    assert fetched.amount == -475.50
    assert fetched.notes == "Included annual fee"


def test_credit_due_override_unique_on_card_and_due_date(app):
    card = CreditCard(
        name="Amex Business",
        is_default=True,
        statement_close_day=10,
        payment_due_offset_days=20,
    )
    db.session.add(card)
    db.session.flush()

    due_date = datetime.date(2026, 2, 9)
    db.session.add(
        CreditDueOverride(credit_card_id=card.id, due_date=due_date, amount="-475.50")
    )
    db.session.commit()

    db.session.add(
        CreditDueOverride(credit_card_id=card.id, due_date=due_date, amount="-500.00")
    )
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db.session.commit()
    db.session.rollback()

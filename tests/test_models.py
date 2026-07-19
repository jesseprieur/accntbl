import datetime

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    CadenceType,
    CheckingAccount,
    CreditCardSettings,
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
    db.session.add(User(username="jesse", password_hash="hashed"))
    db.session.commit()

    user = User.query.filter_by(username="jesse").one()
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
        CreditCardSettings(
            name="Default Credit Card",
            statement_close_day=15,
            payment_due_offset_days=21,
            starting_balance="250.00",
        )
    )
    db.session.commit()

    settings = CreditCardSettings.query.one()
    assert settings.statement_close_day == 15
    assert settings.payment_due_offset_days == 21


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
        cash_amount="2000.00",
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
            cash_amount="-75.25",
            date=datetime.date(2026, 7, 19),
        )
    )
    db.session.commit()

    transaction = Transaction.query.one()
    assert transaction.recurring_series_id is None
    assert transaction.occurrence_status is None

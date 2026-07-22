import datetime as dt
from decimal import Decimal

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import CheckingAccount, CreditCardSettings, User


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        db.session.add(
            User(username="anita", password_hash=generate_password_hash("secret123"))
        )
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    client = app.test_client()
    client.post("/login", data={"username": "anita", "password": "secret123"})
    return client


def test_settings_index_requires_login(app):
    anon_client = app.test_client()
    response = anon_client.get("/settings/")
    assert response.status_code == 302


def test_settings_index_renders_with_no_data(client):
    response = client.get("/settings/")
    assert response.status_code == 200


def test_create_checking_account(client, app):
    response = client.post(
        "/settings/checking-accounts",
        data={
            "name": "Primary Checking",
            "starting_balance": "1000.50",
            "as_of_date": "2026-07-01",
        },
    )
    assert response.status_code == 302

    with app.app_context():
        account = CheckingAccount.query.filter_by(name="Primary Checking").one()
        assert account.starting_balance == Decimal("1000.50")
        assert account.as_of_date.isoformat() == "2026-07-01"


def test_create_checking_account_rejects_invalid_balance(client, app):
    client.post(
        "/settings/checking-accounts",
        data={
            "name": "Bad Account",
            "starting_balance": "not-a-number",
            "as_of_date": "2026-07-01",
        },
    )

    with app.app_context():
        assert CheckingAccount.query.filter_by(name="Bad Account").one_or_none() is None


def test_update_checking_account(client, app):
    with app.app_context():
        account = CheckingAccount(
            name="Old Name", starting_balance=Decimal("10.00"), as_of_date=dt.date(2026, 1, 1)
        )
        db.session.add(account)
        db.session.commit()
        account_id = account.id

    response = client.post(
        f"/settings/checking-accounts/{account_id}",
        data={
            "name": "New Name",
            "starting_balance": "500.00",
            "as_of_date": "2026-07-01",
        },
    )
    assert response.status_code == 302

    with app.app_context():
        account = CheckingAccount.query.get(account_id)
        assert account.name == "New Name"
        assert account.starting_balance == Decimal("500.00")


def test_delete_checking_account(client, app):
    with app.app_context():
        account = CheckingAccount(
            name="To Delete", starting_balance=Decimal("10.00"), as_of_date=dt.date(2026, 1, 1)
        )
        db.session.add(account)
        db.session.commit()
        account_id = account.id

    response = client.post(f"/settings/checking-accounts/{account_id}/delete")
    assert response.status_code == 302

    with app.app_context():
        assert CheckingAccount.query.get(account_id) is None


def test_create_credit_card_settings(client, app):
    response = client.post(
        "/settings/credit-card",
        data={
            "name": "Default Credit Card",
            "statement_close_day": "15",
            "payment_due_offset_days": "20",
            "starting_balance": "250.00",
        },
    )
    assert response.status_code == 302

    with app.app_context():
        settings = CreditCardSettings.query.one()
        assert settings.statement_close_day == 15
        assert settings.payment_due_offset_days == 20
        assert settings.starting_balance == Decimal("250.00")


def test_update_credit_card_settings_overwrites_singleton(client, app):
    with app.app_context():
        db.session.add(
            CreditCardSettings(
                id=1,
                name="Old Card",
                statement_close_day=1,
                payment_due_offset_days=10,
                starting_balance=Decimal("0.00"),
            )
        )
        db.session.commit()

    client.post(
        "/settings/credit-card",
        data={
            "name": "Updated Card",
            "statement_close_day": "20",
            "payment_due_offset_days": "25",
            "starting_balance": "100.00",
        },
    )

    with app.app_context():
        assert CreditCardSettings.query.count() == 1
        settings = CreditCardSettings.query.one()
        assert settings.name == "Updated Card"
        assert settings.statement_close_day == 20


def test_credit_card_settings_rejects_invalid_close_day(client, app):
    client.post(
        "/settings/credit-card",
        data={
            "name": "Default Credit Card",
            "statement_close_day": "40",
            "payment_due_offset_days": "20",
        },
    )

    with app.app_context():
        assert CreditCardSettings.query.first() is None

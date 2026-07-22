import datetime as dt
from decimal import Decimal

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import CheckingAccount, CreditCardSettings, Transaction, User


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


def test_window_requires_login(app):
    anon_client = app.test_client()
    response = anon_client.get("/transactions/window")
    assert response.status_code == 302


def test_window_defaults_to_range_around_today(client):
    response = client.get("/transactions/window")
    assert response.status_code == 200
    data = response.get_json()
    assert data["start"] == (dt.date.today() - dt.timedelta(days=30)).isoformat()
    assert data["end"] == (dt.date.today() + dt.timedelta(days=90)).isoformat()
    assert data["rows"] == []


def test_window_rejects_start_after_end(client):
    response = client.get(
        "/transactions/window", query_string={"start": "2026-08-01", "end": "2026-07-01"}
    )
    assert response.status_code == 400


def test_window_rejects_malformed_date(client):
    response = client.get("/transactions/window", query_string={"start": "not-a-date"})
    assert response.status_code == 400


def test_window_returns_rows_within_range_with_running_total(client, app):
    with app.app_context():
        db.session.add(CheckingAccount(
            name="Primary", starting_balance=Decimal("100.00"), as_of_date=dt.date(2026, 1, 1)
        ))
        db.session.add(Transaction(
            name="Paycheck", cash_amount=Decimal("500.00"), date=dt.date(2026, 7, 10)
        ))
        db.session.add(Transaction(
            name="Rent", cash_amount=Decimal("-400.00"), date=dt.date(2026, 7, 15)
        ))
        # Outside the requested window, but must still count toward baseline math.
        db.session.add(Transaction(
            name="Old expense", cash_amount=Decimal("-50.00"), date=dt.date(2026, 6, 1)
        ))
        db.session.commit()

    response = client.get(
        "/transactions/window",
        query_string={"start": "2026-07-01", "end": "2026-07-31"},
    )
    assert response.status_code == 200
    data = response.get_json()

    names = [row["name"] for row in data["rows"]]
    assert names == ["Paycheck", "Rent"]

    paycheck, rent = data["rows"]
    assert paycheck["running_total"] == "550.00"
    assert paycheck["is_negative"] is False
    assert rent["running_total"] == "150.00"
    assert rent["is_negative"] is False
    assert rent["is_virtual"] is False


def test_window_includes_virtual_credit_card_payment_rows(client, app):
    with app.app_context():
        db.session.add(CheckingAccount(
            name="Primary", starting_balance=Decimal("1000.00"), as_of_date=dt.date(2026, 1, 1)
        ))
        db.session.add(CreditCardSettings(
            id=1,
            name="Default Credit Card",
            statement_close_day=15,
            payment_due_offset_days=10,
            starting_balance=Decimal("0"),
        ))
        db.session.add(Transaction(
            name="Groceries", credit_amount=Decimal("75.00"), date=dt.date(2026, 7, 5)
        ))
        db.session.commit()

    response = client.get(
        "/transactions/window",
        query_string={"start": "2026-07-01", "end": "2026-07-31"},
    )
    data = response.get_json()

    virtual_rows = [row for row in data["rows"] if row["is_virtual"]]
    assert len(virtual_rows) == 1
    assert virtual_rows[0]["name"] == "Default Credit Card Payment"
    assert virtual_rows[0]["date"] == "2026-07-25"
    assert virtual_rows[0]["cash_amount"] == "-75.00"
    assert virtual_rows[0]["id"] is None


def test_window_pagination_stitches_to_match_a_single_wide_fetch(client, app):
    """The infinite-scroll UI fetches adjacent narrow windows (older-past,
    newer-future) as the user scrolls, rather than one wide window. Each
    fetch must agree with what a single wide fetch would have returned,
    including running totals, or scrolling would show inconsistent numbers.
    """
    with app.app_context():
        db.session.add(CheckingAccount(
            name="Primary", starting_balance=Decimal("1000.00"), as_of_date=dt.date(2026, 1, 1)
        ))
        for i in range(6):
            db.session.add(Transaction(
                name=f"Txn {i}",
                cash_amount=Decimal("-25.00"),
                date=dt.date(2026, 7, 1) + dt.timedelta(days=i * 10),
            ))
        db.session.commit()

    wide = client.get(
        "/transactions/window",
        query_string={"start": "2026-07-01", "end": "2026-08-20"},
    ).get_json()

    past = client.get(
        "/transactions/window",
        query_string={"start": "2026-07-01", "end": "2026-07-25"},
    ).get_json()
    future = client.get(
        "/transactions/window",
        query_string={"start": "2026-07-26", "end": "2026-08-20"},
    ).get_json()

    stitched_rows = past["rows"] + future["rows"]
    assert stitched_rows == wide["rows"]
    assert len(wide["rows"]) == 6

import datetime as dt
from decimal import Decimal

import pytest
from werkzeug.security import generate_password_hash

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


def test_update_requires_login(app):
    with app.app_context():
        txn = Transaction(name="Rent", cash_amount=Decimal("-400.00"), date=dt.date(2026, 7, 15))
        db.session.add(txn)
        db.session.commit()
        txn_id = txn.id

    anon_client = app.test_client()
    response = anon_client.patch(f"/transactions/{txn_id}", json={"name": "New name"})
    assert response.status_code == 302


def test_update_one_off_transaction_fields(client, app):
    with app.app_context():
        txn = Transaction(name="Rent", cash_amount=Decimal("-400.00"), date=dt.date(2026, 7, 15))
        db.session.add(txn)
        db.session.commit()
        txn_id = txn.id

    response = client.patch(
        f"/transactions/{txn_id}",
        json={
            "name": "Rent (updated)",
            "cash_amount": "-425.00",
            "date": "2026-07-16",
            "notes": "raised rent",
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["name"] == "Rent (updated)"
    assert data["cash_amount"] == "-425.00"
    assert data["date"] == "2026-07-16"
    assert data["notes"] == "raised rent"
    assert data["occurrence_status"] is None

    with app.app_context():
        updated = Transaction.query.get(txn_id)
        assert updated.name == "Rent (updated)"
        assert updated.cash_amount == Decimal("-425.00")
        assert updated.date == dt.date(2026, 7, 16)


def test_update_rejects_blank_name(client, app):
    with app.app_context():
        txn = Transaction(name="Rent", cash_amount=Decimal("-400.00"), date=dt.date(2026, 7, 15))
        db.session.add(txn)
        db.session.commit()
        txn_id = txn.id

    response = client.patch(f"/transactions/{txn_id}", json={"name": "   "})
    assert response.status_code == 400


def test_update_rejects_malformed_amount(client, app):
    with app.app_context():
        txn = Transaction(name="Rent", cash_amount=Decimal("-400.00"), date=dt.date(2026, 7, 15))
        db.session.add(txn)
        db.session.commit()
        txn_id = txn.id

    response = client.patch(f"/transactions/{txn_id}", json={"cash_amount": "not-a-number"})
    assert response.status_code == 400


def test_update_detaches_attached_series_occurrence(client, app):
    with app.app_context():
        series = RecurringSeries(
            name="Paycheck",
            kind=Kind.cash,
            amount=Decimal("500.00"),
            cadence_type=CadenceType.monthly,
            start_date=dt.date(2026, 7, 1),
        )
        db.session.add(series)
        db.session.commit()

        txn = Transaction(
            name="Paycheck",
            cash_amount=Decimal("500.00"),
            date=dt.date(2026, 7, 1),
            recurring_series_id=series.id,
            occurrence_status=OccurrenceStatus.attached,
        )
        db.session.add(txn)
        db.session.commit()
        txn_id = txn.id

    response = client.patch(f"/transactions/{txn_id}", json={"cash_amount": "550.00"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["occurrence_status"] == "detached"

    with app.app_context():
        updated = Transaction.query.get(txn_id)
        assert updated.occurrence_status == OccurrenceStatus.detached


def test_update_leaves_skipped_occurrence_status_untouched(client, app):
    with app.app_context():
        series = RecurringSeries(
            name="Paycheck",
            kind=Kind.cash,
            amount=Decimal("500.00"),
            cadence_type=CadenceType.monthly,
            start_date=dt.date(2026, 7, 1),
        )
        db.session.add(series)
        db.session.commit()

        txn = Transaction(
            name="Paycheck",
            cash_amount=Decimal("500.00"),
            date=dt.date(2026, 7, 1),
            recurring_series_id=series.id,
            occurrence_status=OccurrenceStatus.skipped,
        )
        db.session.add(txn)
        db.session.commit()
        txn_id = txn.id

    response = client.patch(f"/transactions/{txn_id}", json={"notes": "note"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["occurrence_status"] == "skipped"


def test_delete_requires_login(app):
    with app.app_context():
        txn = Transaction(name="Rent", cash_amount=Decimal("-400.00"), date=dt.date(2026, 7, 15))
        db.session.add(txn)
        db.session.commit()
        txn_id = txn.id

    anon_client = app.test_client()
    response = anon_client.delete(f"/transactions/{txn_id}")
    assert response.status_code == 302


def test_delete_one_off_transaction_hard_deletes(client, app):
    with app.app_context():
        txn = Transaction(name="Rent", cash_amount=Decimal("-400.00"), date=dt.date(2026, 7, 15))
        db.session.add(txn)
        db.session.commit()
        txn_id = txn.id

    response = client.delete(f"/transactions/{txn_id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["deleted"] is True

    with app.app_context():
        assert Transaction.query.get(txn_id) is None


def test_delete_attached_series_occurrence_detaches_instead_of_deleting(client, app):
    with app.app_context():
        series = RecurringSeries(
            name="Paycheck",
            kind=Kind.cash,
            amount=Decimal("500.00"),
            cadence_type=CadenceType.monthly,
            start_date=dt.date(2026, 7, 1),
        )
        db.session.add(series)
        db.session.commit()

        txn = Transaction(
            name="Paycheck",
            cash_amount=Decimal("500.00"),
            date=dt.date(2026, 7, 1),
            recurring_series_id=series.id,
            occurrence_status=OccurrenceStatus.attached,
        )
        db.session.add(txn)
        db.session.commit()
        txn_id = txn.id

    response = client.delete(f"/transactions/{txn_id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["deleted"] is False
    assert data["occurrence_status"] == "detached"

    with app.app_context():
        updated = Transaction.query.get(txn_id)
        assert updated is not None
        assert updated.occurrence_status == OccurrenceStatus.detached


def test_delete_missing_transaction_returns_404(client):
    response = client.delete("/transactions/999999")
    assert response.status_code == 404


def _make_series_occurrence(app, occurrence_status=OccurrenceStatus.attached):
    with app.app_context():
        series = RecurringSeries(
            name="Paycheck",
            kind=Kind.cash,
            amount=Decimal("500.00"),
            cadence_type=CadenceType.monthly,
            start_date=dt.date(2026, 7, 1),
        )
        db.session.add(series)
        db.session.commit()

        txn = Transaction(
            name="Paycheck",
            cash_amount=Decimal("500.00"),
            date=dt.date(2026, 7, 1),
            recurring_series_id=series.id,
            occurrence_status=occurrence_status,
        )
        db.session.add(txn)
        db.session.commit()
        return txn.id


def test_skip_requires_login(app):
    txn_id = _make_series_occurrence(app)
    anon_client = app.test_client()
    response = anon_client.post(f"/transactions/{txn_id}/skip")
    assert response.status_code == 302


def test_skip_sets_occurrence_status_skipped(client, app):
    txn_id = _make_series_occurrence(app)

    response = client.post(f"/transactions/{txn_id}/skip")
    assert response.status_code == 200
    data = response.get_json()
    assert data["occurrence_status"] == "skipped"

    with app.app_context():
        updated = Transaction.query.get(txn_id)
        assert updated.occurrence_status == OccurrenceStatus.skipped


def test_skip_rejects_one_off_transaction(client, app):
    with app.app_context():
        txn = Transaction(name="Rent", cash_amount=Decimal("-400.00"), date=dt.date(2026, 7, 15))
        db.session.add(txn)
        db.session.commit()
        txn_id = txn.id

    response = client.post(f"/transactions/{txn_id}/skip")
    assert response.status_code == 400


def test_skip_removes_row_from_window_and_running_total(client, app):
    txn_id = _make_series_occurrence(app)
    with app.app_context():
        db.session.add(CheckingAccount(
            name="Primary", starting_balance=Decimal("0.00"), as_of_date=dt.date(2026, 1, 1)
        ))
        db.session.commit()

    client.post(f"/transactions/{txn_id}/skip")

    response = client.get(
        "/transactions/window",
        query_string={"start": "2026-07-01", "end": "2026-07-31"},
    )
    data = response.get_json()
    assert data["rows"] == []


def test_window_include_skipped_returns_skipped_row_without_running_total(client, app):
    txn_id = _make_series_occurrence(app)
    with app.app_context():
        db.session.add(CheckingAccount(
            name="Primary", starting_balance=Decimal("0.00"), as_of_date=dt.date(2026, 1, 1)
        ))
        db.session.commit()

    client.post(f"/transactions/{txn_id}/skip")

    response = client.get(
        "/transactions/window",
        query_string={"start": "2026-07-01", "end": "2026-07-31", "include_skipped": "1"},
    )
    data = response.get_json()
    assert len(data["rows"]) == 1
    row = data["rows"][0]
    assert row["id"] == txn_id
    assert row["occurrence_status"] == "skipped"
    assert row["running_total"] is None


def test_unskip_requires_login(app):
    txn_id = _make_series_occurrence(app, occurrence_status=OccurrenceStatus.skipped)
    anon_client = app.test_client()
    response = anon_client.post(f"/transactions/{txn_id}/unskip")
    assert response.status_code == 302


def test_unskip_sets_occurrence_status_attached(client, app):
    txn_id = _make_series_occurrence(app, occurrence_status=OccurrenceStatus.skipped)

    response = client.post(f"/transactions/{txn_id}/unskip")
    assert response.status_code == 200
    data = response.get_json()
    assert data["occurrence_status"] == "attached"

    with app.app_context():
        updated = Transaction.query.get(txn_id)
        assert updated.occurrence_status == OccurrenceStatus.attached


def test_unskip_rejects_non_skipped_transaction(client, app):
    txn_id = _make_series_occurrence(app, occurrence_status=OccurrenceStatus.attached)

    response = client.post(f"/transactions/{txn_id}/unskip")
    assert response.status_code == 400


def test_unskip_missing_transaction_returns_404(client):
    response = client.post("/transactions/999999/unskip")
    assert response.status_code == 404


def test_skip_missing_transaction_returns_404(client):
    response = client.post("/transactions/999999/skip")
    assert response.status_code == 404


def test_create_requires_login(app):
    anon_client = app.test_client()
    response = anon_client.post(
        "/transactions",
        json={"name": "Rent", "date": "2026-07-15", "cash_amount": "-400.00"},
    )
    assert response.status_code == 302


def test_create_one_off_transaction(client, app):
    response = client.post(
        "/transactions",
        json={"name": "Rent", "date": "2026-07-15", "cash_amount": "-400.00", "notes": "monthly"},
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["name"] == "Rent"
    assert data["date"] == "2026-07-15"
    assert data["cash_amount"] == "-400.00"
    assert data["recurring_series_id"] is None

    with app.app_context():
        created = Transaction.query.get(data["id"])
        assert created is not None
        assert created.name == "Rent"
        assert created.cash_amount == Decimal("-400.00")
        assert created.date == dt.date(2026, 7, 15)
        assert created.notes == "monthly"
        assert created.recurring_series_id is None


def test_create_appears_in_window_with_running_total(client, app):
    with app.app_context():
        db.session.add(CheckingAccount(
            name="Primary", starting_balance=Decimal("1000.00"), as_of_date=dt.date(2026, 1, 1)
        ))
        db.session.commit()

    client.post(
        "/transactions",
        json={"name": "Rent", "date": "2026-07-15", "cash_amount": "-400.00"},
    )

    response = client.get(
        "/transactions/window",
        query_string={"start": "2026-07-01", "end": "2026-07-31"},
    )
    data = response.get_json()
    assert len(data["rows"]) == 1
    assert data["rows"][0]["name"] == "Rent"
    assert data["rows"][0]["running_total"] == "600.00"


def test_create_requires_name(client):
    response = client.post(
        "/transactions",
        json={"name": "  ", "date": "2026-07-15", "cash_amount": "-400.00"},
    )
    assert response.status_code == 400


def test_create_requires_date(client):
    response = client.post(
        "/transactions",
        json={"name": "Rent", "cash_amount": "-400.00"},
    )
    assert response.status_code == 400


def test_create_rejects_invalid_amount(client):
    response = client.post(
        "/transactions",
        json={"name": "Rent", "date": "2026-07-15", "cash_amount": "not-a-number"},
    )
    assert response.status_code == 400

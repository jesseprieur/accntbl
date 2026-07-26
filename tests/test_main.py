import datetime as dt

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import User


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


def test_index_requires_login(app):
    anon_client = app.test_client()
    response = anon_client.get("/")
    assert response.status_code == 302


def test_index_renders_transactions_window_centered_on_today(client):
    response = client.get("/")
    assert response.status_code == 200

    body = response.get_data(as_text=True)
    today = dt.date.today().isoformat()

    assert f'data-today="{today}"' in body
    assert 'data-window-url="/transactions/window"' in body
    assert 'id="transactions-tbody"' in body
    assert "table.js" in body


def test_index_uses_bootstrap_toggle_buttons_for_kind(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert 'class="btn-check" name="kind" id="add-transaction-kind-cash"' in body
    assert 'class="btn-check" name="kind" id="add-transaction-kind-credit"' in body
    assert 'class="form-check-input" type="radio" name="kind"' not in body


def test_recurring_series_page_uses_bootstrap_toggle_buttons_for_kind(client):
    response = client.get("/recurring-series")
    body = response.get_data(as_text=True)

    assert 'class="btn-check" name="kind" id="add-series-kind-cash"' in body
    assert 'class="btn-check" name="kind" id="edit-series-kind-cash"' in body
    assert 'class="form-check-input" type="radio" name="kind"' not in body


def test_base_layout_loads_bootstrap_icons(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert "bootstrap-icons" in body


def test_index_buttons_use_icons(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert '<i class="bi bi-plus-lg"></i> Add transaction' in body
    assert '<i class="bi bi-arrow-repeat"></i> Recurring Series' in body
    assert '<i class="bi bi-gear"></i> Settings' in body
    assert '<i class="bi bi-box-arrow-right"></i> Log out' in body


def test_settings_page_buttons_use_icons(client):
    response = client.get("/settings/")
    body = response.get_data(as_text=True)

    assert '<i class="bi bi-arrow-left"></i> Back' in body
    assert '<i class="bi bi-plus-lg"></i> Add' in body


def test_recurring_series_page_buttons_use_icons(client):
    response = client.get("/recurring-series")
    body = response.get_data(as_text=True)

    assert '<i class="bi bi-plus-lg"></i> Add recurring series' in body
    assert '<i class="bi bi-arrow-left"></i> Back' in body

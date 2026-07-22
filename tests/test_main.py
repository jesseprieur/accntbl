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

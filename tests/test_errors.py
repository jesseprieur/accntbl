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


def test_unknown_page_route_renders_404_html(client):
    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404
    assert b"Page not found" in response.data


def test_unknown_transactions_route_returns_json_404(client):
    response = client.get("/transactions/999999/does-not-exist")
    assert response.status_code == 404
    assert response.is_json
    assert response.get_json() == {"error": "Not found."}

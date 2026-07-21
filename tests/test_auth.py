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
    return app.test_client()


def test_index_redirects_to_login_when_not_authenticated(client):
    response = client.get("/")

    assert response.status_code == 302
    assert response.headers["Location"] == "/login?next=/"


def test_login_with_valid_credentials_redirects_to_index(client):
    response = client.post(
        "/login", data={"username": "anita", "password": "secret123"}
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_login_establishes_session_allowing_access_to_protected_route(client):
    client.post("/login", data={"username": "anita", "password": "secret123"})

    response = client.get("/")

    assert response.status_code == 200


def test_login_with_invalid_password_does_not_authenticate(client):
    response = client.post(
        "/login", data={"username": "anita", "password": "wrongpassword"}
    )

    assert response.status_code == 200
    assert b"Invalid username or password" in response.data

    protected_response = client.get("/")
    assert protected_response.status_code == 302


def test_login_with_unknown_username_does_not_authenticate(client):
    response = client.post(
        "/login", data={"username": "nobody", "password": "secret123"}
    )

    assert response.status_code == 200
    assert b"Invalid username or password" in response.data


def test_login_redirects_to_next_url_when_provided(client):
    response = client.post(
        "/login?next=/some/other/path",
        data={"username": "anita", "password": "secret123"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/some/other/path"


def test_logout_clears_session_and_reprotects_index(client):
    client.post("/login", data={"username": "anita", "password": "secret123"})
    assert client.get("/").status_code == 200

    logout_response = client.post("/logout")
    assert logout_response.status_code == 302
    assert logout_response.headers["Location"] == "/login"

    assert client.get("/").status_code == 302

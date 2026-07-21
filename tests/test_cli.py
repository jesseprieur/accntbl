from werkzeug.security import check_password_hash

import pytest

from app import create_app
from app.extensions import db
from app.models import User


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


def test_create_user_seeds_a_new_user(app, runner):
    result = runner.invoke(
        args=["create-user"],
        input="anita\nsecret123\nsecret123\n",
    )

    assert result.exit_code == 0
    with app.app_context():
        user = User.query.filter_by(username="anita").one()
        assert check_password_hash(user.password_hash, "secret123")


def test_create_user_resets_password_for_existing_username(app, runner):
    with app.app_context():
        db.session.add(User(username="anita", password_hash="stale-hash"))
        db.session.commit()

    result = runner.invoke(
        args=["create-user"],
        input="anita\nnewpassword\nnewpassword\n",
    )

    assert result.exit_code == 0
    with app.app_context():
        users = User.query.filter_by(username="anita").all()
        assert len(users) == 1
        assert check_password_hash(users[0].password_hash, "newpassword")


def test_create_user_requires_matching_password_confirmation(app, runner):
    result = runner.invoke(
        args=["create-user"],
        input="anita\nsecret123\nmismatch\n",
    )

    assert result.exit_code != 0
    with app.app_context():
        assert User.query.filter_by(username="anita").one_or_none() is None

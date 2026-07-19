from app import create_app
from app.extensions import db


def test_create_app_returns_configured_flask_app():
    app = create_app("testing")

    assert app.testing is True
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"


def test_create_app_initializes_db_extension_against_app():
    app = create_app("testing")

    with app.app_context():
        assert db.engine is not None
        # A trivial query proves the engine is actually connectable, not
        # just configured.
        db.session.execute(db.text("SELECT 1"))


def test_development_config_is_default_when_no_env_name_given(monkeypatch):
    monkeypatch.delenv("FLASK_ENV", raising=False)

    app = create_app()

    assert app.config["DEBUG"] is True
    assert app.testing is False

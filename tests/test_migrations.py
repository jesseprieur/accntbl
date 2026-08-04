import os
import tempfile

import pytest
from flask_migrate import upgrade
from sqlalchemy import inspect

from app import create_app
from app.extensions import db


@pytest.fixture
def app():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    app = create_app("testing")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{path}"
    yield app
    os.remove(path)


def test_alembic_upgrade_head_creates_all_model_tables(app):
    with app.app_context():
        upgrade()

        inspector = inspect(db.engine)
        actual_tables = set(inspector.get_table_names())

    expected_tables = set(db.metadata.tables.keys()) | {"alembic_version"}
    assert expected_tables <= actual_tables

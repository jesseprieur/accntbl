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


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


def test_alembic_upgrade_head_creates_all_model_tables(app):
    with app.app_context():
        upgrade()

        inspector = inspect(db.engine)
        actual_tables = set(inspector.get_table_names())

    expected_tables = set(db.metadata.tables.keys()) | {"alembic_version"}
    assert expected_tables <= actual_tables


def test_db_downgrade_dash_one_without_separator_is_misparsed_as_an_option(app, runner):
    # Regression guard for the README's documented rollback command: a bare
    # "-1" revision arg is swallowed by Click as an option flag, not passed
    # through to Alembic as the target revision.
    runner.invoke(args=["db", "upgrade"])

    result = runner.invoke(args=["db", "downgrade", "-1"])

    assert result.exit_code != 0
    assert "No such option" in result.output


def test_db_downgrade_dash_one_with_separator_reverts_the_only_migration(app, runner):
    # This is the syntax README.md actually documents:
    # `flask db downgrade -- -1`
    runner.invoke(args=["db", "upgrade"])

    result = runner.invoke(args=["db", "downgrade", "--", "-1"])
    assert result.exit_code == 0

    with app.app_context():
        inspector = inspect(db.engine)
        actual_tables = set(inspector.get_table_names())

    model_tables = set(db.metadata.tables.keys())
    # The schema is a single migration (see
    # migrations/versions/8b1c4f9a2e3d_create_full_schema.py), so "one step
    # back" reverts all the way to base — this test exists to guard the
    # `-- -1` CLI syntax itself, not incremental-migration behavior.
    assert not (model_tables & actual_tables)


def test_db_downgrade_to_base_reverts_all_tables(app, runner):
    runner.invoke(args=["db", "upgrade"])

    result = runner.invoke(args=["db", "downgrade", "base"])
    assert result.exit_code == 0

    with app.app_context():
        inspector = inspect(db.engine)
        actual_tables = set(inspector.get_table_names())

    model_tables = set(db.metadata.tables.keys())
    assert not (model_tables & actual_tables)

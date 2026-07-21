from flask import Flask

from app.config import get_config
from app.extensions import db, migrate


def create_app(config_name=None):
    app = Flask(__name__)
    app.config.from_object(get_config(config_name)())

    db.init_app(app)
    migrate.init_app(app, db)

    from app import models  # noqa: F401  (registers models with db.metadata)
    from app.cli import register_cli

    register_cli(app)

    return app

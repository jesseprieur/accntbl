from flask import Flask

from app.config import get_config
from app.extensions import db, migrate


def create_app(config_name=None):
    app = Flask(__name__)
    app.config.from_object(get_config(config_name)())

    db.init_app(app)
    migrate.init_app(app, db)

    from app import models  # noqa: F401  (registers models with db.metadata)
    from app.auth import auth_bp
    from app.main import main_bp
    from app.settings import settings_bp
    from app.transactions import transactions_bp
    from app.cli import register_cli

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(transactions_bp)
    register_cli(app)

    return app

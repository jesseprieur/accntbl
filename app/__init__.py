from flask import Flask

from app.config import get_config
from app.extensions import db, migrate


def create_app(config_name=None):
    app = Flask(__name__)
    app.config.from_object(get_config(config_name)())

    db.init_app(app)
    migrate.init_app(app, db)

    from app import models  # noqa: F401  (registers models with db.metadata)
    from app.routes.auth import auth_bp
    from app.routes.backup import backup_bp
    from app.routes.categories import categories_bp
    from app.routes.checking_accounts import checking_accounts_bp
    from app.routes.credit_cards import credit_cards_bp
    from app.routes.main import main_bp
    from app.routes.recurring_series import recurring_series_bp
    from app.routes.settings import settings_bp
    from app.routes.statistics import statistics_bp
    from app.routes.transactions import transactions_bp
    from app.cli import register_cli
    from app.errors import register_error_handlers

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(checking_accounts_bp)
    app.register_blueprint(credit_cards_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(backup_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(recurring_series_bp)
    app.register_blueprint(statistics_bp)
    register_cli(app)
    register_error_handlers(app)

    return app

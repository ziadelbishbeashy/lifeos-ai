"""LifeOS Flask application factory and local development entry point."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from flask import Flask
from click import ClickException
from werkzeug.middleware.proxy_fix import ProxyFix

from config import (
    CONFIG_BY_NAME,
    get_config_name,
    validate_config,
)
from database import db
from extensions import init_extensions, login_manager
from error_handlers import register_error_handlers
from logging_config import configure_logging
from security import init_security
from models import User
from routes.ai_routes import ai_bp
from routes.analytics_routes import analytics_bp
from routes.auth_routes import auth_bp
from routes.dashboard_routes import register_dashboard_routes
from routes.focus_routes import focus_bp
from routes.note_routes import note_bp
from routes.notification_routes import notification_bp
from routes.project_routes import project_bp
from routes.task_routes import task_bp
from routes.document_routes import document_bp
from services.scheduler_service import (
    run_notification_check_once,
    start_notification_scheduler,
)


load_dotenv()


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def register_blueprints(app: Flask) -> None:
    """Register the existing LifeOS feature modules."""

    app.register_blueprint(auth_bp)
    app.register_blueprint(project_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(focus_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(note_bp)
    app.register_blueprint(document_bp)

def register_commands(app: Flask) -> None:
    """Register small maintenance commands for local development."""

    @app.cli.command("init-db")
    def init_db_command():
        """Create missing tables in a development database.

        Public deployments should use Flask-Migrate revisions instead.
        """

        if app.config.get("ENV_NAME") == "production":
            raise ClickException(
                "init-db is disabled in production. Use reviewed migrations."
            )

        db.create_all()
        print("LifeOS database tables are ready.")

    @app.cli.command("notifications-once")
    def notifications_once_command():
        """Run one notification cycle outside the web request process."""

        result = run_notification_check_once(app)
        print(result)

    @app.cli.command("diagnose")
    def diagnose_command():
        """Print non-secret deployment diagnostics."""

        print(f"environment={app.config.get('ENV_NAME')}")
        print(f"database_configured={bool(app.config.get('SQLALCHEMY_DATABASE_URI'))}")
        print(f"storage_backend={app.config.get('STORAGE_BACKEND')}")
        print(f"job_backend={app.config.get('JOB_BACKEND')}")
        print(f"scheduler_enabled={bool(app.config.get('ENABLE_EMAIL_SCHEDULER'))}")


def create_app(
    config_name: str | None = None,
    test_config: dict | None = None,
) -> Flask:
    """Create and configure a LifeOS application instance."""

    selected_config = config_name or get_config_name()
    config_class = CONFIG_BY_NAME.get(
        selected_config,
        CONFIG_BY_NAME["development"],
    )

    application = Flask(__name__)
    application.config.from_object(config_class)

    if test_config:
        application.config.update(test_config)

    validate_config(application)
    configure_logging(application)
    if application.config.get("TRUST_PROXY_HEADERS"):
        application.wsgi_app = ProxyFix(
            application.wsgi_app,
            x_for=1,
            x_proto=1,
            x_host=1,
            x_port=1,
        )
    init_extensions(application)
    register_blueprints(application)
    register_dashboard_routes(application)
    register_error_handlers(application)
    init_security(application)
    register_commands(application)

    return application


if __name__ == "__main__":
    app = create_app()

    if app.config.get("AUTO_CREATE_DB"):
        with app.app_context():
            db.create_all()

    if app.config.get("ENABLE_EMAIL_SCHEDULER"):
        start_notification_scheduler(app)

    if os.getenv("SHOW_REGISTERED_ROUTES", "false").lower() == "true":
        print("\nREGISTERED ROUTES:")
        for rule in app.url_map.iter_rules():
            print(rule)

    app.run(
        debug=bool(app.config.get("DEBUG")),
        use_reloader=False,
    )

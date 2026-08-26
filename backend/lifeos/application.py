"""LifeOS application factory for Foundation V2."""

from __future__ import annotations

from click import ClickException
from flask import Flask
from pathlib import Path
from werkzeug.middleware.proxy_fix import ProxyFix

from lifeos.api.v1 import register_api_v1
from lifeos.core.config import CONFIG_BY_NAME, get_config_name, validate_config
from lifeos.core.database import db
from lifeos.core.extensions import init_extensions, login_manager

from error_handlers import register_error_handlers
from logging_config import configure_logging
from jobs.document_ocr import register_document_ocr_job
from models import User
from routes.ai_routes import ai_bp
from routes.analytics_routes import analytics_bp
from routes.auth_routes import auth_bp
from routes.dashboard_routes import register_dashboard_routes
from routes.document_routes import document_bp
from routes.focus_routes import focus_bp
from routes.note_routes import note_bp
from routes.notification_routes import notification_bp
from routes.project_routes import project_bp
from routes.task_routes import task_bp
from security import init_security
from services.scheduler_service import run_notification_check_once


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def register_legacy_web_blueprints(app: Flask) -> None:
    """Register proven web controllers used by the React UI parity bridge."""

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
    @app.cli.command("init-db")
    def init_db_command():
        """Create missing tables only for local/development bootstrapping."""

        if app.config.get("ENV_NAME") == "production":
            raise ClickException(
                "init-db is disabled in production. Use a reviewed PostgreSQL baseline/migration."
            )
        db.create_all()
        print("LifeOS database tables are ready.")

    @app.cli.command("notifications-once")
    def notifications_once_command():
        result = run_notification_check_once(app)
        print(result)

    @app.cli.command("diagnose")
    def diagnose_command():
        uri = str(app.config.get("SQLALCHEMY_DATABASE_URI") or "")
        if uri.startswith("postgresql"):
            database_family = "postgresql"
        elif uri.startswith("mssql"):
            database_family = "legacy-sqlserver"
        elif uri.startswith("sqlite"):
            database_family = "sqlite"
        else:
            database_family = "other"
        print(f"environment={app.config.get('ENV_NAME')}")
        print(f"database_family={database_family}")
        print(f"database_configured={bool(uri)}")
        print(f"storage_backend={app.config.get('STORAGE_BACKEND')}")
        print(f"job_backend={app.config.get('JOB_BACKEND')}")
        print(f"scheduler_enabled={bool(app.config.get('ENABLE_EMAIL_SCHEDULER'))}")
        print("architecture=foundation-v2")


def create_app(
    config_name: str | None = None,
    test_config: dict | None = None,
) -> Flask:
    selected_config = config_name or get_config_name()
    config_class = CONFIG_BY_NAME.get(selected_config, CONFIG_BY_NAME["development"])

    backend_dir = Path(__file__).resolve().parents[1]
    application = Flask(
        __name__,
        template_folder=str(backend_dir / "templates"),
        static_folder=str(backend_dir / "static"),
        static_url_path="/static",
    )
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
    register_document_ocr_job()
    register_legacy_web_blueprints(application)
    register_api_v1(application)
    register_dashboard_routes(application)
    register_error_handlers(application)
    init_security(application)
    register_commands(application)

    return application

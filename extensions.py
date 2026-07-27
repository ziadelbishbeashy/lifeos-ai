"""Central Flask extension instances used by the application factory."""

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

from database import db


login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()

login_manager.login_view = "auth_bp.login"
login_manager.login_message = "Please log in to access your workspace."
login_manager.login_message_category = "info"


def init_extensions(app) -> None:
    """Attach extensions to a Flask application instance."""

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

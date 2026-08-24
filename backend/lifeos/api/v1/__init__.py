"""LifeOS API v1 registration.

API v1 is split by product boundary so the React migration can grow without
recreating the legacy route-file monolith.
"""

from lifeos.api.v1.documents import documents_api_bp
from lifeos.api.v1.projects import projects_api_bp
from lifeos.api.v1.routes import api_v1_bp
from lifeos.api.v1.legacy_ui import legacy_ui_api_bp
from lifeos.api.v1.tasks import tasks_api_bp


def register_api_v1(app) -> None:
    app.register_blueprint(api_v1_bp)
    app.register_blueprint(projects_api_bp)
    app.register_blueprint(tasks_api_bp)
    app.register_blueprint(documents_api_bp)
    app.register_blueprint(legacy_ui_api_bp)


__all__ = [
    "api_v1_bp",
    "projects_api_bp",
    "tasks_api_bp",
    "documents_api_bp",
    "legacy_ui_api_bp",
    "register_api_v1",
]

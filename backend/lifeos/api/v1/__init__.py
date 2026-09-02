"""LifeOS API v1 registration.

API v1 is split by product boundary so the React migration can grow without
recreating the legacy route-file monolith.
"""

from lifeos.api.v1.documents import documents_api_bp
from lifeos.api.v1.experience import experience_api_bp
from lifeos.api.v1.document_collections import document_collections_api_bp
from lifeos.api.v1.notes import notes_api_bp
from lifeos.api.v1.focus import focus_api_bp
from lifeos.api.v1.analytics import analytics_api_bp
from lifeos.api.v1.agent import agent_api_bp
from lifeos.api.v1.automations import automations_api_bp
from lifeos.api.v1.notifications import notifications_api_bp
from lifeos.api.v1.modules import modules_api_bp
from lifeos.api.v1.intelligence import intelligence_api_bp
from lifeos.api.v1.projects import projects_api_bp
from lifeos.api.v1.routes import api_v1_bp
from lifeos.api.v1.tasks import tasks_api_bp


def register_api_v1(app) -> None:
    app.register_blueprint(api_v1_bp)
    app.register_blueprint(experience_api_bp)
    app.register_blueprint(projects_api_bp)
    app.register_blueprint(tasks_api_bp)
    app.register_blueprint(documents_api_bp)
    app.register_blueprint(document_collections_api_bp)
    app.register_blueprint(modules_api_bp)
    app.register_blueprint(intelligence_api_bp)
    app.register_blueprint(automations_api_bp)
    app.register_blueprint(notes_api_bp)
    app.register_blueprint(focus_api_bp)
    app.register_blueprint(analytics_api_bp)
    app.register_blueprint(agent_api_bp)
    app.register_blueprint(notifications_api_bp)


__all__ = [
    "api_v1_bp",
    "experience_api_bp",
    "projects_api_bp",
    "tasks_api_bp",
    "documents_api_bp",
    "document_collections_api_bp",
    "modules_api_bp",
    "intelligence_api_bp",
    "automations_api_bp",
    "notes_api_bp",
    "focus_api_bp",
    "analytics_api_bp",
    "agent_api_bp",
    "notifications_api_bp",
    "register_api_v1",
]

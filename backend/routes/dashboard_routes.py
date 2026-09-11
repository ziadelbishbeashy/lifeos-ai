"""Landing page and Today's Workspace routes.

The routes are registered with their original endpoint names (``landing`` and
``dashboard``) so existing templates and redirects continue to work.
"""

from flask import redirect, render_template, url_for
from flask_login import current_user, login_required

from services.dashboard_service import build_dashboard_context
from services.system_health_service import database_is_ready


def landing():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    return render_template("landing.html")


@login_required
def dashboard():
    context = build_dashboard_context(current_user.id)
    return render_template(
        "dashboard.html",
        **context,
    )


def health():
    """Lightweight liveness check that does not touch external services."""

    return {"status": "ok", "service": "lifeos"}, 200


def readiness():
    """Readiness check used by deployment slots and container health probes."""

    ready = database_is_ready()
    return (
        {
            "status": "ready" if ready else "not_ready",
            "service": "lifeos",
            "database": "ok" if ready else "unavailable",
        },
        200 if ready else 503,
    )


def register_dashboard_routes(app) -> None:
    app.add_url_rule("/", endpoint="landing", view_func=landing)
    app.add_url_rule(
        "/dashboard",
        endpoint="dashboard",
        view_func=dashboard,
    )
    app.add_url_rule("/health", endpoint="health", view_func=health)
    app.add_url_rule(
        "/health/ready",
        endpoint="readiness",
        view_func=readiness,
    )

"""React UI parity bridge for the proven LifeOS web experience.

This module lets the React frontend own the browser entry point without
rewriting every proven Jinja screen and interaction at once. The bridge
reuses the existing legacy controllers/services and returns their exact HTML,
JSON or file responses through the versioned API boundary.

Why this exists
---------------
LifeOS already has a large, tested UI surface (Document Brain, Focus, Notes,
notifications, analytics, etc.). Rebuilding all of it in one blind JSX rewrite
would be a regression risk. The React parity host therefore renders the exact
existing view output while keeping Flask as the authoritative workflow layer.
Native React feature components can replace parity-rendered screens one at a
time later without changing backend contracts or visual behavior.
"""

from __future__ import annotations

from urllib.parse import quote, urlsplit

from flask import Blueprint, current_app, jsonify, make_response, request
from flask_login import current_user
from werkzeug.exceptions import MethodNotAllowed, NotFound


legacy_ui_api_bp = Blueprint(
    "legacy_ui_api",
    __name__,
    url_prefix="/api/v1/legacy-proxy",
)

# Only the established browser-facing controllers are reachable through this
# compatibility bridge. API endpoints, health checks, static files and future
# internal routes cannot be recursively dispatched through it.
_ALLOWED_ENDPOINTS = {
    "landing",
    "dashboard",
}
_ALLOWED_PREFIXES = (
    "auth_bp.",
    "project_bp.",
    "task_bp.",
    "notification_bp.",
    "focus_bp.",
    "analytics_bp.",
    "ai_bp.",
    "note_bp.",
    "document_bp.",
)
_PUBLIC_ENDPOINTS = {
    "landing",
    "auth_bp.login",
    "auth_bp.register",
}


def _is_allowed_endpoint(endpoint: str) -> bool:
    return endpoint in _ALLOWED_ENDPOINTS or endpoint.startswith(_ALLOWED_PREFIXES)


def _target_path() -> str:
    """Return a safe local path requested by the React parity host.

    Normal fetches use the header so the original query string stays available
    in ``request.args`` for the legacy controller. GET-only browser resources
    such as the PDF iframe may use ``__legacy_path`` because they cannot attach
    custom headers.
    """

    target = (
        request.headers.get("X-LifeOS-Legacy-Path")
        or request.args.get("__legacy_path")
        or ""
    ).strip()

    if not target:
        raise NotFound()

    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        raise NotFound()

    path = parsed.path or "/"
    if not path.startswith("/") or path.startswith("//"):
        raise NotFound()

    if path.startswith(("/api/", "/static/")):
        raise NotFound()

    return path


def _match_legacy_endpoint(target_path: str):
    adapter = current_app.url_map.bind_to_environ(request.environ)
    try:
        rule, values = adapter.match(
            path_info=target_path,
            method=request.method,
            return_rule=True,
        )
        endpoint = rule.endpoint
    except (NotFound, MethodNotAllowed):
        raise NotFound() from None

    if not _is_allowed_endpoint(endpoint):
        raise NotFound()

    return rule, endpoint, values


def _frontend_redirect(location: str, target_path: str) -> str:
    """Normalize a backend redirect so the React host can navigate to it."""

    parsed = urlsplit(location or "")
    if parsed.scheme or parsed.netloc:
        return location

    path = parsed.path or "/"
    query = parsed.query

    # Flask-Login sees the proxy URL rather than the original browser page.
    # Replace that generated ``next`` value with the real requested screen.
    if path == "/login" and "next=" in query:
        return f"/login?next={quote(target_path, safe='/')}"

    return location or "/"


def _normalize_response(result, target_path: str):
    response = make_response(result)

    # A fetch would otherwise automatically follow a legacy redirect to the
    # Vite/React origin and return index.html. Convert it to a lightweight
    # signal the React host can handle explicitly.
    if 300 <= response.status_code < 400:
        location = response.headers.get("Location")
        if location:
            redirect_to = _frontend_redirect(location, target_path)
            bridged = make_response("", 204)
            bridged.headers["X-LifeOS-Legacy-Redirect"] = redirect_to
            bridged.headers["Cache-Control"] = "no-store, max-age=0"
            return bridged

    response.headers.setdefault("Cache-Control", "no-store, max-age=0")
    response.headers.setdefault("X-LifeOS-UI-Parity", "legacy-controller")
    return response


@legacy_ui_api_bp.route("", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def legacy_proxy():
    """Dispatch one proven web controller through the React API boundary."""

    target_path = _target_path()
    rule, endpoint, values = _match_legacy_endpoint(target_path)

    if endpoint not in _PUBLIC_ENDPOINTS and not current_user.is_authenticated:
        response = make_response("", 204)
        response.headers["X-LifeOS-Legacy-Redirect"] = (
            f"/login?next={quote(target_path, safe='/')}"
        )
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    view = current_app.view_functions.get(endpoint)
    if view is None:
        raise NotFound()

    # Make template-level request.endpoint / request.blueprint checks behave
    # exactly as they do on the original route. This is especially important
    # for active navigation styling and Focus Mode body classes.
    original_rule = request.url_rule
    original_view_args = request.view_args
    try:
        request.url_rule = rule
        request.view_args = values
        result = view(**values)
    finally:
        request.url_rule = original_rule
        request.view_args = original_view_args

    return _normalize_response(result, target_path)


@legacy_ui_api_bp.get("/meta")
def legacy_proxy_meta():
    """Small diagnostic contract used by tests and deployment checks."""

    return jsonify(
        {
            "mode": "react-ui-parity",
            "backend": "flask-service-workflows",
            "rendering": "compatibility-controller",
            "native_api": "/api/v1",
        }
    )

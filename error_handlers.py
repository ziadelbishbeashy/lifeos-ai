"""Central error responses for LifeOS."""

from __future__ import annotations

from flask import jsonify, render_template, request
from flask_wtf.csrf import CSRFError

from database import db


def _wants_json() -> bool:
    return (
        request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
    )


def _response(status_code: int, title: str, message: str):
    if _wants_json():
        return jsonify({"error": title, "message": message}), status_code

    return (
        render_template(
            "errors/error.html",
            status_code=status_code,
            title=title,
            message=message,
        ),
        status_code,
    )


def register_error_handlers(app) -> None:
    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        return _response(
            400,
            "Your form expired",
            "Refresh the page and submit the action again.",
        )

    @app.errorhandler(403)
    def handle_forbidden(_error):
        return _response(
            403,
            "Access denied",
            "You do not have permission to perform this action.",
        )

    @app.errorhandler(404)
    def handle_not_found(_error):
        return _response(
            404,
            "Page not found",
            "The page may have moved or no longer exists.",
        )

    @app.errorhandler(413)
    def handle_upload_too_large(_error):
        max_mb = max(1, app.config.get("MAX_CONTENT_LENGTH", 0) // 1024 // 1024)
        return _response(
            413,
            "File is too large",
            f"The current upload limit is {max_mb} MB.",
        )

    @app.errorhandler(500)
    def handle_server_error(error):
        db.session.rollback()
        app.logger.exception("Unhandled LifeOS error", exc_info=error)
        return _response(
            500,
            "LifeOS could not complete the request",
            "Nothing was intentionally changed. Please try again.",
        )

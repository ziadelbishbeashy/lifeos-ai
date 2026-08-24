"""Shared HTTP helpers for the versioned React API boundary."""

from __future__ import annotations

from functools import wraps

from flask import jsonify, request
from flask_login import current_user


def api_auth_required(view):
    """Return JSON 401s instead of Flask-Login redirects for API requests."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify(
                {
                    "error": "authentication_required",
                    "message": "Please log in to continue.",
                }
            ), 401
        return view(*args, **kwargs)

    return wrapped


def json_body() -> dict:
    """Return one JSON object or an empty mapping for malformed/non-object JSON."""

    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def validation_error(message: str):
    return jsonify({"error": "validation_error", "message": message}), 400


def not_found(message: str):
    return jsonify({"error": "not_found", "message": message}), 404


def persistence_error(message: str):
    return jsonify({"error": "persistence_error", "message": message}), 500

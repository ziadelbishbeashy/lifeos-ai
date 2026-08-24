"""Core versioned JSON API boundary used by the React frontend.

Feature-specific endpoints live in sibling modules (projects.py, tasks.py,
documents.py). This file intentionally keeps session/auth/dashboard concerns
small so feature routes do not become another monolith.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from flask_login import current_user, login_user, logout_user
from flask_wtf.csrf import generate_csrf
from sqlalchemy.exc import SQLAlchemyError

from lifeos.api.v1.common import api_auth_required, json_body
from lifeos.domains.auth.facade import (
    AccountCreationError,
    DuplicateEmailError,
    authenticate_user,
    build_registration_input,
    claim_legacy_projects,
    create_user,
    normalize_email,
    validate_registration,
)
from lifeos.domains.dashboard.facade import (
    build_dashboard_context,
    serialize_dashboard_context,
)


api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


def _user_payload(user) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
    }


@api_v1_bp.get("/health")
def health():
    return jsonify({"status": "ok", "service": "lifeos", "api": "v1"})


@api_v1_bp.get("/meta")
def meta():
    return jsonify(
        {
            "name": "LifeOS",
            "architecture": "foundation-v2",
            "api_version": "v1",
            "preferred_database": "postgresql",
            "legacy_web_enabled": True,
            "frontend_migration": "react-ui-parity-complete",
            "native_frontend_slices": ["projects"],
        }
    )


@api_v1_bp.get("/csrf")
def csrf_token():
    """Issue the CSRF token React must send with unsafe API requests."""

    return jsonify({"csrf_token": generate_csrf()})


@api_v1_bp.get("/session")
def session_state():
    if not current_user.is_authenticated:
        return jsonify({"authenticated": False, "user": None})

    return jsonify(
        {
            "authenticated": True,
            "user": _user_payload(current_user),
        }
    )


@api_v1_bp.post("/auth/login")
def login():
    if current_user.is_authenticated:
        return jsonify(
            {
                "authenticated": True,
                "user": _user_payload(current_user),
            }
        )

    payload = json_body()
    email = normalize_email(payload.get("email"))
    password = str(payload.get("password") or "")
    remember = payload.get("remember") is True

    user = authenticate_user(email, password)
    if user is None:
        return jsonify(
            {
                "error": "invalid_credentials",
                "message": "Incorrect email or password.",
            }
        ), 401

    try:
        claim_legacy_projects(user)
    except SQLAlchemyError:
        current_app.logger.exception(
            "LifeOS could not claim legacy projects during API login."
        )

    login_user(user, remember=remember)

    return jsonify(
        {
            "authenticated": True,
            "user": _user_payload(user),
        }
    )


@api_v1_bp.post("/auth/register")
def register():
    if current_user.is_authenticated:
        return jsonify(
            {
                "authenticated": True,
                "user": _user_payload(current_user),
            }
        )

    payload = json_body()
    registration = build_registration_input(
        name=payload.get("name"),
        email=payload.get("email"),
        password=payload.get("password"),
        confirm_password=payload.get("confirm_password"),
    )

    validation_message = validate_registration(registration)
    if validation_message:
        return jsonify(
            {
                "error": "validation_error",
                "message": validation_message,
            }
        ), 400

    try:
        user = create_user(registration)
    except DuplicateEmailError:
        return jsonify(
            {
                "error": "duplicate_email",
                "message": "An account with this email already exists.",
            }
        ), 409
    except AccountCreationError:
        current_app.logger.exception(
            "LifeOS could not create a user account through API v1."
        )
        return jsonify(
            {
                "error": "account_creation_failed",
                "message": "The account could not be created.",
            }
        ), 500

    login_user(user)

    return jsonify(
        {
            "authenticated": True,
            "user": _user_payload(user),
        }
    ), 201


@api_v1_bp.post("/auth/logout")
@api_auth_required
def logout():
    logout_user()
    return jsonify({"authenticated": False, "user": None})


@api_v1_bp.get("/dashboard")
@api_auth_required
def dashboard():
    context = build_dashboard_context(current_user.id)
    return jsonify(serialize_dashboard_context(context))

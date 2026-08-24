"""Versioned JSON API boundary for the React migration.

Foundation V2 deliberately starts with read-only endpoints. Mutating endpoints
should be added domain-by-domain with explicit validation, CSRF/auth strategy,
and contract tests instead of exposing legacy route internals directly.
"""

from __future__ import annotations

from functools import wraps

from flask import Blueprint, jsonify
from flask_login import current_user

from models import Project
from services.document_access_service import list_owned_documents


api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


def api_auth_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"error": "authentication_required"}), 401
        return view(*args, **kwargs)
    return wrapped


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
            "frontend_migration": "incremental",
        }
    )


@api_v1_bp.get("/session")
def session_state():
    if not current_user.is_authenticated:
        return jsonify({"authenticated": False, "user": None})

    return jsonify(
        {
            "authenticated": True,
            "user": {
                "id": current_user.id,
                "name": current_user.name,
                "email": current_user.email,
            },
        }
    )


@api_v1_bp.get("/projects")
@api_auth_required
def projects():
    rows = (
        Project.query
        .filter_by(user_id=current_user.id)
        .order_by(Project.updated_at.desc(), Project.id.desc())
        .all()
    )
    return jsonify(
        {
            "items": [
                {
                    "id": row.id,
                    "title": row.title,
                    "status": row.status,
                    "priority": row.priority,
                    "progress": row.progress,
                    "deadline": row.deadline.isoformat() if row.deadline else None,
                }
                for row in rows
            ]
        }
    )


@api_v1_bp.get("/documents")
@api_auth_required
def documents():
    rows = list_owned_documents(current_user.id)
    return jsonify(
        {
            "items": [
                {
                    "id": row.id,
                    "project_id": row.project_id,
                    "filename": row.filename,
                    "version_label": row.version_label,
                    "is_current_version": bool(row.is_current_version),
                    "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
                }
                for row in rows
            ]
        }
    )

"""Private Tutor V1 API."""

from __future__ import annotations

from flask import Blueprint, jsonify
from flask_login import current_user

from lifeos.api.v1.common import api_auth_required, json_body, not_found, validation_error
from lifeos.api.v1.serializers import serialize_module
from services.module_service import list_owned_modules
from services.private_tutor_service import (
    PrivateTutorError,
    PrivateTutorNotFoundError,
    PrivateTutorNotReadyError,
    PrivateTutorValidationError,
    generate_owned_tutor_session,
    grade_owned_tutor_quiz,
    list_owned_tutor_sessions,
    require_owned_tutor_session,
    serialize_tutor_session,
)


tutor_api_bp = Blueprint("api_v1_tutor", __name__, url_prefix="/api/v1/tutor")


@tutor_api_bp.get("")
@api_auth_required
def tutor_home_route():
    modules = list_owned_modules(current_user.id)
    sessions = list_owned_tutor_sessions(user_id=current_user.id, limit=12)
    return jsonify({
        "modules": [serialize_module(item, include_resources=True) for item in modules],
        "recent_sessions": [serialize_tutor_session(item) for item in sessions],
        "modes": ["explain", "summarize", "quiz", "practice", "flashcards"],
        "difficulties": ["beginner", "intermediate", "advanced"],
    })


@tutor_api_bp.post("/sessions")
@api_auth_required
def create_tutor_session_route():
    payload = json_body()
    try:
        module_id = int(payload.get("module_id"))
    except (TypeError, ValueError):
        return validation_error("Choose a module to study.")
    lecture_id = payload.get("lecture_id")
    if lecture_id not in (None, "", 0, "0"):
        try:
            lecture_id = int(lecture_id)
        except (TypeError, ValueError):
            return validation_error("Choose a valid lecture.")
    else:
        lecture_id = None
    try:
        row = generate_owned_tutor_session(
            user_id=current_user.id,
            module_id=module_id,
            lecture_id=lecture_id,
            mode=payload.get("mode"),
            topic=payload.get("topic"),
            request_text=payload.get("request_text"),
            difficulty=payload.get("difficulty", "intermediate"),
            question_count=payload.get("question_count", 5),
        )
    except PrivateTutorNotFoundError:
        return not_found("Module or lecture not found.")
    except PrivateTutorValidationError as error:
        return validation_error(str(error))
    except PrivateTutorNotReadyError as error:
        return jsonify({"error": "tutor_material_not_ready", "message": str(error)}), 409
    except PrivateTutorError as error:
        return jsonify({"error": "tutor_generation_failed", "message": str(error)}), 503
    return jsonify({"session": serialize_tutor_session(row)}), 201


@tutor_api_bp.get("/sessions/<int:session_id>")
@api_auth_required
def tutor_session_route(session_id: int):
    try:
        row = require_owned_tutor_session(session_id=session_id, user_id=current_user.id)
    except PrivateTutorNotFoundError:
        return not_found("Tutor session not found.")
    return jsonify({"session": serialize_tutor_session(row)})


@tutor_api_bp.post("/sessions/<int:session_id>/grade")
@api_auth_required
def grade_tutor_session_route(session_id: int):
    payload = json_body()
    try:
        grade = grade_owned_tutor_quiz(
            session_id=session_id,
            user_id=current_user.id,
            answers=payload.get("answers") or {},
        )
        row = require_owned_tutor_session(session_id=session_id, user_id=current_user.id)
    except PrivateTutorNotFoundError:
        return not_found("Tutor session not found.")
    except PrivateTutorValidationError as error:
        return validation_error(str(error))
    except PrivateTutorError as error:
        return jsonify({"error": "tutor_grade_failed", "message": str(error)}), 503
    return jsonify({
        "grade": grade.to_dict(),
        "session": serialize_tutor_session(row),
    })

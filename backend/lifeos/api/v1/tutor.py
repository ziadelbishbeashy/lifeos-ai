"""Private Tutor V1 API."""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user

from models import PrivateTutorSession

from lifeos.api.v1.common import api_auth_required, json_body, not_found, validation_error
from lifeos.api.v1.serializers import serialize_module
from services.module_service import list_owned_modules
from services.private_tutor_personalization_service import (
    TutorPersonalizationNotFoundError,
    TutorPersonalizationValidationError,
    build_owned_course_profile,
    resolve_owned_study_intent,
)
from services.private_tutor_service import (
    PrivateTutorError,
    PrivateTutorNotFoundError,
    PrivateTutorNotReadyError,
    PrivateTutorValidationError,
    generate_owned_mistake_review,
    generate_owned_quiz_retry,
    generate_owned_tutor_follow_up,
    generate_owned_tutor_session,
    grade_owned_tutor_quiz,
    list_owned_tutor_conversation,
    list_owned_tutor_mastery,
    list_owned_tutor_sessions,
    require_owned_tutor_session,
    serialize_tutor_mastery,
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
        "difficulties": ["adaptive", "beginner", "intermediate", "advanced"],
    })


@tutor_api_bp.post("/resolve-study")
@api_auth_required
def tutor_resolve_study_route():
    payload = json_body()
    try:
        resolution = resolve_owned_study_intent(
            user_id=current_user.id, request_text=payload.get("request_text")
        )
        if resolution.get("status") == "matched" and resolution.get("selected_module_id"):
            resolution["profile"] = build_owned_course_profile(
                user_id=current_user.id, module_id=int(resolution["selected_module_id"])
            )
    except TutorPersonalizationValidationError as error:
        return validation_error(str(error))
    except TutorPersonalizationNotFoundError:
        return not_found("Module not found.")
    return jsonify({"resolution": resolution})


@tutor_api_bp.get("/modules/<int:module_id>/profile")
@api_auth_required
def tutor_module_profile_route(module_id: int):
    try:
        profile = build_owned_course_profile(user_id=current_user.id, module_id=module_id)
    except TutorPersonalizationNotFoundError:
        return not_found("Module not found.")
    return jsonify({"profile": profile})


@tutor_api_bp.post("/sessions")
@api_auth_required
def create_tutor_session_route():
    payload = json_body()
    module_id = payload.get("module_id")
    if module_id in (None, "", 0, "0") and payload.get("request_text"):
        try:
            resolution = resolve_owned_study_intent(
                user_id=current_user.id, request_text=payload.get("request_text")
            )
        except TutorPersonalizationValidationError as error:
            return validation_error(str(error))
        if resolution.get("status") != "matched" or not resolution.get("selected_module_id"):
            return jsonify({
                "error": "tutor_module_resolution_required",
                "message": resolution.get("message") or "Choose a module to study.",
                "resolution": resolution,
            }), 409
        module_id = resolution["selected_module_id"]
    try:
        module_id = int(module_id)
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
            difficulty=payload.get("difficulty", "adaptive"),
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


@tutor_api_bp.get("/progress")
@api_auth_required
def tutor_progress_route():
    module_id = request.args.get("module_id")
    parsed_module_id = None
    if module_id not in (None, ""):
        try:
            parsed_module_id = int(module_id)
        except (TypeError, ValueError):
            return validation_error("Choose a valid module.")
    rows = list_owned_tutor_mastery(user_id=current_user.id, module_id=parsed_module_id, limit=60)
    quiz_query = PrivateTutorSession.query.filter_by(user_id=current_user.id, mode="quiz", status="graded")
    if parsed_module_id is not None:
        quiz_query = quiz_query.filter_by(module_id=parsed_module_id)
    attempts = quiz_query.order_by(PrivateTutorSession.created_at.desc()).limit(12).all()
    return jsonify({
        "mastery": [serialize_tutor_mastery(row) for row in rows],
        "quiz_history": [serialize_tutor_session(row) for row in attempts],
    })


@tutor_api_bp.get("/conversations/<string:conversation_key>")
@api_auth_required
def tutor_conversation_route(conversation_key: str):
    try:
        rows = list_owned_tutor_conversation(conversation_key=conversation_key, user_id=current_user.id)
    except PrivateTutorValidationError as error:
        return validation_error(str(error))
    if not rows:
        return not_found("Tutor conversation not found.")
    return jsonify({"sessions": [serialize_tutor_session(row) for row in rows]})


@tutor_api_bp.post("/sessions/<int:session_id>/follow-up")
@api_auth_required
def tutor_follow_up_route(session_id: int):
    payload = json_body()
    try:
        row = generate_owned_tutor_follow_up(session_id=session_id, user_id=current_user.id, request_text=payload.get("request_text"))
    except PrivateTutorNotFoundError:
        return not_found("Tutor session not found.")
    except PrivateTutorValidationError as error:
        return validation_error(str(error))
    except PrivateTutorNotReadyError as error:
        return jsonify({"error": "tutor_material_not_ready", "message": str(error)}), 409
    except PrivateTutorError as error:
        return jsonify({"error": "tutor_follow_up_failed", "message": str(error)}), 503
    return jsonify({"session": serialize_tutor_session(row)}), 201


@tutor_api_bp.post("/sessions/<int:session_id>/review-mistakes")
@api_auth_required
def tutor_review_mistakes_route(session_id: int):
    try:
        row = generate_owned_mistake_review(session_id=session_id, user_id=current_user.id)
    except PrivateTutorNotFoundError:
        return not_found("Tutor session not found.")
    except PrivateTutorValidationError as error:
        return validation_error(str(error))
    except PrivateTutorNotReadyError as error:
        return jsonify({"error": "tutor_material_not_ready", "message": str(error)}), 409
    except PrivateTutorError as error:
        return jsonify({"error": "tutor_review_failed", "message": str(error)}), 503
    return jsonify({"session": serialize_tutor_session(row)}), 201


@tutor_api_bp.post("/sessions/<int:session_id>/retry-quiz")
@api_auth_required
def tutor_retry_quiz_route(session_id: int):
    try:
        row = generate_owned_quiz_retry(session_id=session_id, user_id=current_user.id)
    except PrivateTutorNotFoundError:
        return not_found("Tutor session not found.")
    except PrivateTutorValidationError as error:
        return validation_error(str(error))
    except PrivateTutorNotReadyError as error:
        return jsonify({"error": "tutor_material_not_ready", "message": str(error)}), 409
    except PrivateTutorError as error:
        return jsonify({"error": "tutor_retry_failed", "message": str(error)}), 503
    return jsonify({"session": serialize_tutor_session(row)}), 201

from __future__ import annotations

from flask import Blueprint, jsonify
from flask_login import current_user

from lifeos.api.v1.common import api_auth_required, json_body, not_found, persistence_error, validation_error
from lifeos.api.v1.serializers import json_safe, serialize_focus_session, serialize_task
from services.focus_service import (
    FocusConflictError,
    FocusNotFoundError,
    FocusPersistenceError,
    FocusValidationError,
    add_distraction,
    begin_review,
    cancel_session,
    convert_distraction_to_task,
    extend_session,
    finish_session,
    get_focus_insights,
    get_focus_page_data,
    pause_session,
    require_owned_distraction,
    require_owned_session,
    resume_session,
    start_session,
)

focus_api_bp = Blueprint("api_v1_focus", __name__, url_prefix="/api/v1/focus")


def _service_error(error):
    if isinstance(error, FocusNotFoundError):
        return not_found("Focus item not found.")
    if isinstance(error, (FocusValidationError, FocusConflictError)):
        return validation_error(str(error))
    return persistence_error("LifeOS could not update Focus Mode.")


@focus_api_bp.get("")
@api_auth_required
def focus_state():
    data = get_focus_page_data(current_user.id)
    return jsonify({
        "tasks": [serialize_task(task) for task in data.tasks],
        "active_session": serialize_focus_session(data.active_session),
        "elapsed_seconds": data.elapsed_seconds,
        "today_minutes": data.today_minutes,
    })


@focus_api_bp.get("/insights")
@api_auth_required
def focus_insights():
    return jsonify(json_safe(get_focus_insights(current_user.id)))


@focus_api_bp.post("/start")
@api_auth_required
def focus_start():
    payload = json_body()
    try:
        session = start_session(
            current_user.id,
            payload.get("task_id"),
            payload.get("duration"),
            payload.get("goal"),
        )
    except (FocusValidationError, FocusConflictError, FocusPersistenceError) as error:
        return _service_error(error)
    return jsonify({"session": serialize_focus_session(session)}), 201


@focus_api_bp.post("/<int:session_id>/pause")
@api_auth_required
def focus_pause(session_id: int):
    try:
        session = pause_session(require_owned_session(session_id, current_user.id))
    except (FocusNotFoundError, FocusConflictError, FocusPersistenceError) as error:
        return _service_error(error)
    return jsonify({"session": serialize_focus_session(session)})


@focus_api_bp.post("/<int:session_id>/resume")
@api_auth_required
def focus_resume(session_id: int):
    try:
        session = resume_session(require_owned_session(session_id, current_user.id))
    except (FocusNotFoundError, FocusConflictError, FocusPersistenceError) as error:
        return _service_error(error)
    return jsonify({"session": serialize_focus_session(session)})


@focus_api_bp.post("/<int:session_id>/extend")
@api_auth_required
def focus_extend(session_id: int):
    try:
        session = extend_session(require_owned_session(session_id, current_user.id))
    except (FocusNotFoundError, FocusConflictError, FocusPersistenceError) as error:
        return _service_error(error)
    return jsonify({"session": serialize_focus_session(session)})


@focus_api_bp.post("/<int:session_id>/distractions")
@api_auth_required
def focus_distraction(session_id: int):
    payload = json_body()
    try:
        session = require_owned_session(session_id, current_user.id)
        distraction = add_distraction(session, current_user.id, payload.get("content"))
    except (FocusNotFoundError, FocusConflictError, FocusValidationError, FocusPersistenceError) as error:
        return _service_error(error)
    return jsonify({"item": json_safe({
        "id": distraction.id,
        "content": distraction.content,
        "captured_at": distraction.captured_at,
        "converted_task_id": distraction.converted_task_id,
    })}), 201


@focus_api_bp.post("/distractions/<int:distraction_id>/convert")
@api_auth_required
def focus_convert_distraction(distraction_id: int):
    try:
        distraction = require_owned_distraction(distraction_id, current_user.id)
        task, already_linked = convert_distraction_to_task(distraction, current_user.id)
    except (FocusNotFoundError, FocusConflictError, FocusPersistenceError) as error:
        return _service_error(error)
    return jsonify({"task": serialize_task(task), "already_linked": already_linked})


@focus_api_bp.post("/<int:session_id>/review")
@api_auth_required
def focus_review(session_id: int):
    try:
        session = begin_review(require_owned_session(session_id, current_user.id))
    except (FocusNotFoundError, FocusConflictError, FocusPersistenceError) as error:
        return _service_error(error)
    return jsonify({"session": serialize_focus_session(session), "review_requested": True})


@focus_api_bp.post("/<int:session_id>/finish")
@api_auth_required
def focus_finish(session_id: int):
    payload = json_body()
    try:
        session = finish_session(
            require_owned_session(session_id, current_user.id),
            payload.get("notes"),
            payload.get("goal_result"),
            payload.get("focus_rating"),
            bool(payload.get("complete_task")),
        )
    except (FocusNotFoundError, FocusConflictError, FocusValidationError, FocusPersistenceError) as error:
        return _service_error(error)
    return jsonify({"session": serialize_focus_session(session)})


@focus_api_bp.post("/<int:session_id>/cancel")
@api_auth_required
def focus_cancel(session_id: int):
    try:
        session = cancel_session(require_owned_session(session_id, current_user.id))
    except (FocusNotFoundError, FocusConflictError, FocusPersistenceError) as error:
        return _service_error(error)
    return jsonify({"session": serialize_focus_session(session)})

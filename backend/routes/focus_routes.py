"""HTTP routes for LifeOS Focus Mode."""

from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from services.focus_service import (
    FocusConflictError,
    FocusNotFoundError,
    FocusPersistenceError,
    FocusValidationError,
    add_distraction as add_distraction_record,
    begin_review as begin_review_session,
    cancel_session,
    convert_distraction_to_task as convert_distraction_record,
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


focus_bp = Blueprint("focus_bp", __name__, url_prefix="/focus")


@focus_bp.before_request
@login_required
def protect_focus_routes():
    return None


def _owned_session_or_404(session_id: int):
    try:
        return require_owned_session(session_id, current_user.id)
    except FocusNotFoundError:
        abort(404)


def _owned_distraction_or_404(distraction_id: int):
    try:
        return require_owned_distraction(distraction_id, current_user.id)
    except FocusNotFoundError:
        abort(404)


@focus_bp.route("/")
def focus_mode():
    data = get_focus_page_data(current_user.id)
    return render_template(
        "focus_mode.html",
        tasks=data.tasks,
        active_session=data.active_session,
        elapsed_seconds=data.elapsed_seconds,
        today_minutes=data.today_minutes,
        review_requested=bool(data.active_session)
        and request.args.get("review") == "1",
    )


@focus_bp.route("/insights")
def insights():
    return render_template(
        "focus_insights.html",
        **get_focus_insights(current_user.id),
    )


@focus_bp.route("/start", methods=["POST"])
def start_focus():
    try:
        start_session(
            current_user.id,
            request.form.get("task_id"),
            request.form.get("duration_minutes"),
            request.form.get("goal"),
        )
    except FocusConflictError as error:
        flash(str(error), "warning")
    except FocusPersistenceError:
        current_app.logger.exception("LifeOS could not start a focus session.")
        flash("The focus session could not be started.", "error")
    return redirect(url_for("focus_bp.focus_mode"))


@focus_bp.route("/<int:session_id>/pause", methods=["POST"])
def pause_focus(session_id):
    session = _owned_session_or_404(session_id)
    try:
        session = pause_session(session)
        return jsonify(
            {
                "ok": True,
                "status": session.status,
                "elapsed_seconds": session.elapsed_seconds,
            }
        )
    except FocusPersistenceError:
        current_app.logger.exception("Could not pause focus session %s.", session.id)
        return jsonify({"ok": False, "message": "Could not pause session."}), 500


@focus_bp.route("/<int:session_id>/resume", methods=["POST"])
def resume_focus(session_id):
    session = _owned_session_or_404(session_id)
    try:
        session = resume_session(session)
        return jsonify({"ok": True, "status": session.status})
    except FocusPersistenceError:
        current_app.logger.exception("Could not resume focus session %s.", session.id)
        return jsonify({"ok": False, "message": "Could not resume session."}), 500


@focus_bp.route("/<int:session_id>/extend", methods=["POST"])
def extend_focus(session_id):
    session = _owned_session_or_404(session_id)
    try:
        session = extend_session(session)
        return jsonify({"ok": True, "planned_minutes": session.planned_minutes})
    except FocusConflictError as error:
        return jsonify({"ok": False, "message": str(error)}), 409
    except FocusPersistenceError:
        current_app.logger.exception("Could not extend focus session %s.", session.id)
        return jsonify({"ok": False, "message": "Could not extend session."}), 500


@focus_bp.route("/<int:session_id>/distraction", methods=["POST"])
def add_distraction(session_id):
    session = _owned_session_or_404(session_id)
    payload = request.get_json(silent=True) or request.form
    try:
        thought = add_distraction_record(
            session,
            current_user.id,
            payload.get("content"),
        )
        return jsonify(
            {
                "ok": True,
                "count": session.distraction_count,
                "thought": {"id": thought.id, "content": thought.content},
            }
        )
    except FocusValidationError as error:
        return jsonify({"ok": False, "message": str(error)}), 400
    except FocusConflictError as error:
        return jsonify({"ok": False, "message": str(error)}), 409
    except FocusPersistenceError:
        current_app.logger.exception(
            "Could not save a distraction for focus session %s.",
            session.id,
        )
        return jsonify({"ok": False, "message": "Could not save thought."}), 500


@focus_bp.route("/distractions/<int:thought_id>/convert", methods=["POST"])
def convert_distraction_to_task(thought_id):
    thought = _owned_distraction_or_404(thought_id)
    try:
        task, already_converted = convert_distraction_record(
            thought,
            current_user.id,
        )
        return jsonify(
            {
                "ok": True,
                "task_id": task.id,
                "already_converted": already_converted,
            }
        )
    except FocusPersistenceError:
        current_app.logger.exception(
            "Could not convert distraction %s to a task.",
            thought.id,
        )
        return jsonify({"ok": False, "message": "Could not create task."}), 500


@focus_bp.route("/<int:session_id>/review", methods=["POST"], endpoint="begin_review")
def begin_review(session_id):
    session = _owned_session_or_404(session_id)
    try:
        begin_review_session(session)
    except FocusPersistenceError:
        current_app.logger.exception(
            "Could not begin review for focus session %s.",
            session.id,
        )
        flash("The focus review could not be opened.", "error")
    return redirect(url_for("focus_bp.focus_mode", review=1))


@focus_bp.route("/<int:session_id>/finish", methods=["POST"])
def finish_focus(session_id):
    session = _owned_session_or_404(session_id)
    try:
        finish_session(
            session,
            request.form.get("notes"),
            request.form.get("goal_result"),
            request.form.get("focus_rating"),
            request.form.get("complete_task") == "on",
        )
        flash("Focus session saved.", "success")
    except FocusPersistenceError:
        current_app.logger.exception(
            "Could not finish focus session %s.",
            session.id,
        )
        flash("The focus session could not be saved.", "error")

    destination = (request.form.get("destination") or "focus").strip().lower()
    return redirect(
        url_for("dashboard")
        if destination == "dashboard"
        else url_for("focus_bp.focus_mode")
    )


@focus_bp.route("/<int:session_id>/cancel", methods=["POST"])
def cancel_focus(session_id):
    session = _owned_session_or_404(session_id)
    try:
        cancel_session(session)
        flash("Focus session ended without saving it as completed.", "info")
    except FocusPersistenceError:
        current_app.logger.exception(
            "Could not cancel focus session %s.",
            session.id,
        )
        flash("The focus session could not be ended.", "error")
    return redirect(url_for("focus_bp.focus_mode"))

from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from database import db
from models import FocusDistraction, FocusSession, Task
from services.recurring_task_service import generate_next_occurrence


focus_bp = Blueprint("focus_bp", __name__, url_prefix="/focus")


@focus_bp.before_request
@login_required
def protect_focus_routes():
    return None


def owned_task(task_id):
    if not task_id:
        return None
    return Task.query.filter_by(id=task_id, user_id=current_user.id).first()


def active_session():
    return (
        FocusSession.query
        .filter_by(user_id=current_user.id)
        .filter(FocusSession.status.in_(["running", "paused"]))
        .order_by(FocusSession.created_at.desc())
        .first()
    )


def current_elapsed_seconds(session):
    elapsed = session.elapsed_seconds or 0
    if session.status == "running" and session.started_at:
        elapsed += max(0, int((datetime.utcnow() - session.started_at).total_seconds()))
    return elapsed


def clamp_integer(value, default, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


@focus_bp.route("/")
def focus_mode():
    tasks = (
        Task.query
        .filter_by(user_id=current_user.id)
        .filter(Task.status.notin_(["Completed", "Blocked"]))
        .order_by(Task.deadline.asc(), Task.priority_score.desc())
        .all()
    )

    session = active_session()
    elapsed = current_elapsed_seconds(session) if session else 0

    today_start = datetime.combine(date.today(), datetime.min.time())
    today_sessions = (
        FocusSession.query
        .filter(
            FocusSession.user_id == current_user.id,
            FocusSession.completed_at >= today_start,
            FocusSession.status == "completed",
        )
        .all()
    )
    today_minutes = sum(item.actual_minutes or 0 for item in today_sessions)

    review_requested = bool(session) and request.args.get("review") == "1"

    return render_template(
        "focus_mode.html",
        tasks=tasks,
        active_session=session,
        elapsed_seconds=elapsed,
        today_minutes=today_minutes,
        review_requested=review_requested,
    )


@focus_bp.route("/insights")
def insights():
    now = datetime.utcnow()
    seven_days_ago = datetime.combine(date.today() - timedelta(days=6), datetime.min.time())

    completed = (
        FocusSession.query
        .filter(
            FocusSession.user_id == current_user.id,
            FocusSession.status == "completed",
        )
        .order_by(FocusSession.completed_at.desc())
        .all()
    )

    weekly_sessions = [
        item for item in completed
        if item.completed_at and item.completed_at >= seven_days_ago
    ]
    week_minutes = sum(item.actual_minutes or 0 for item in weekly_sessions)
    week_distractions = sum(item.distraction_count or 0 for item in weekly_sessions)
    rated = [item.focus_rating for item in weekly_sessions if item.focus_rating]
    average_rating = round(sum(rated) / len(rated), 1) if rated else None

    by_day = defaultdict(int)
    for item in weekly_sessions:
        by_day[item.completed_at.date()] += item.actual_minutes or 0

    daily_data = []
    max_minutes = max(by_day.values(), default=0)
    for offset in range(7):
        day = date.today() - timedelta(days=6 - offset)
        minutes = by_day.get(day, 0)
        daily_data.append({
            "label": day.strftime("%a"),
            "date": day.strftime("%d %b"),
            "minutes": minutes,
            "height": round((minutes / max_minutes) * 100) if max_minutes else 0,
        })

    project_totals = defaultdict(int)
    for item in completed:
        if item.task and item.task.project:
            label = item.task.project.title
        else:
            label = "General workspace"
        project_totals[label] += item.actual_minutes or 0

    project_data = sorted(
        ({"name": name, "minutes": minutes} for name, minutes in project_totals.items()),
        key=lambda row: row["minutes"],
        reverse=True,
    )[:5]

    return render_template(
        "focus_insights.html",
        week_minutes=week_minutes,
        week_sessions=len(weekly_sessions),
        week_distractions=week_distractions,
        average_rating=average_rating,
        daily_data=daily_data,
        project_data=project_data,
        recent_sessions=completed[:12],
        generated_at=now,
    )


@focus_bp.route("/start", methods=["POST"])
def start_focus():
    if active_session():
        flash("Finish or cancel the active focus session first.", "warning")
        return redirect(url_for("focus_bp.focus_mode"))

    task = owned_task(request.form.get("task_id"))
    duration = clamp_integer(request.form.get("duration_minutes"), 25, 5, 180)
    goal = (request.form.get("goal") or "").strip()[:500] or None

    title = task.title if task else "General focus session"
    session = FocusSession(
        user_id=current_user.id,
        task_id=task.id if task else None,
        title=title,
        goal=goal,
        planned_minutes=duration,
        status="running",
        started_at=datetime.utcnow(),
    )

    if task and task.status == "Pending":
        task.status = "In Progress"

    db.session.add(session)
    db.session.commit()
    return redirect(url_for("focus_bp.focus_mode"))


@focus_bp.route("/<int:session_id>/pause", methods=["POST"])
def pause_focus(session_id):
    session = FocusSession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()
    if session.status == "running":
        session.elapsed_seconds = current_elapsed_seconds(session)
        session.started_at = None
        session.status = "paused"
        db.session.commit()
    return jsonify({"ok": True, "status": session.status, "elapsed_seconds": session.elapsed_seconds})


@focus_bp.route("/<int:session_id>/resume", methods=["POST"])
def resume_focus(session_id):
    session = FocusSession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()
    if session.status == "paused":
        session.started_at = datetime.utcnow()
        session.status = "running"
        db.session.commit()
    return jsonify({"ok": True, "status": session.status})


@focus_bp.route("/<int:session_id>/extend", methods=["POST"])
def extend_focus(session_id):
    session = FocusSession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()
    if session.status not in ("running", "paused"):
        return jsonify({"ok": False, "message": "This session is no longer active."}), 409

    session.planned_minutes = min((session.planned_minutes or 25) + 5, 240)
    db.session.commit()
    return jsonify({"ok": True, "planned_minutes": session.planned_minutes})


@focus_bp.route("/<int:session_id>/distraction", methods=["POST"])
def add_distraction(session_id):
    session = FocusSession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()
    if session.status not in ("running", "paused"):
        return jsonify({"ok": False, "message": "This session is no longer active."}), 409

    payload = request.get_json(silent=True) or request.form
    content = (payload.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "message": "Write a thought first."}), 400

    thought = FocusDistraction(
        session_id=session.id,
        user_id=current_user.id,
        content=content[:500],
    )
    session.distraction_count = (session.distraction_count or 0) + 1
    db.session.add(thought)
    db.session.commit()

    return jsonify({
        "ok": True,
        "count": session.distraction_count,
        "thought": {"id": thought.id, "content": thought.content},
    })


@focus_bp.route("/distractions/<int:thought_id>/convert", methods=["POST"])
def convert_distraction_to_task(thought_id):
    thought = FocusDistraction.query.filter_by(
        id=thought_id,
        user_id=current_user.id,
    ).first_or_404()

    if thought.converted_task_id:
        return jsonify({
            "ok": True,
            "task_id": thought.converted_task_id,
            "already_converted": True,
        })

    task = Task(
        user_id=current_user.id,
        project_id=None,
        title=thought.content[:200],
        description="Captured from the Focus Mode distraction inbox.",
        importance="Medium",
        difficulty="Low",
        status="Pending",
        priority_score=0,
    )
    db.session.add(task)
    db.session.flush()
    thought.converted_task_id = task.id
    db.session.commit()

    return jsonify({"ok": True, "task_id": task.id})


@focus_bp.route("/<int:session_id>/review", methods=["POST"], endpoint="begin_review")
def begin_review(session_id):
    """Pause the active timer and open the server-rendered review step.

    This endpoint intentionally uses a normal HTML form so ending a session
    still works even when browser JavaScript fails or is disabled.
    """
    session = FocusSession.query.filter_by(
        id=session_id,
        user_id=current_user.id,
    ).first_or_404()

    if session.status == "running":
        session.elapsed_seconds = current_elapsed_seconds(session)
        session.started_at = None
        session.status = "paused"
        db.session.commit()

    return redirect(url_for("focus_bp.focus_mode", review=1))


@focus_bp.route("/<int:session_id>/finish", methods=["POST"])
def finish_focus(session_id):
    session = FocusSession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()

    elapsed = current_elapsed_seconds(session)
    session.elapsed_seconds = elapsed
    session.actual_minutes = max(1, round(elapsed / 60)) if elapsed else 0
    session.status = "completed"
    session.completed_at = datetime.utcnow()
    session.started_at = None
    session.notes = (request.form.get("notes") or "").strip()[:2000] or None

    result = request.form.get("goal_result")
    session.goal_result = result if result in {"full", "partial", "not_yet"} else None
    rating = clamp_integer(request.form.get("focus_rating"), 0, 0, 5)
    session.focus_rating = rating or None

    if session.task and request.form.get("complete_task") == "on":
        session.task.status = "Completed"
        generate_next_occurrence(session.task)

    db.session.commit()
    flash("Focus session saved.", "success")

    destination = (request.form.get("destination") or "focus").strip().lower()
    if destination == "dashboard":
        return redirect(url_for("dashboard"))

    return redirect(url_for("focus_bp.focus_mode"))


@focus_bp.route("/<int:session_id>/cancel", methods=["POST"])
def cancel_focus(session_id):
    session = FocusSession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()
    session.status = "cancelled"
    session.elapsed_seconds = current_elapsed_seconds(session)
    session.actual_minutes = round((session.elapsed_seconds or 0) / 60)
    session.completed_at = datetime.utcnow()
    session.started_at = None
    db.session.commit()
    flash("Focus session ended without saving it as completed.", "info")
    return redirect(url_for("focus_bp.focus_mode"))

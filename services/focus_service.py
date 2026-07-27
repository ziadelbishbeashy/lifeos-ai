"""Focus Mode domain service for LifeOS."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import FocusDistraction, FocusSession, Task
from services.recurring_task_service import generate_next_occurrence


class FocusNotFoundError(LookupError):
    """Raised when a focus entity is not owned by the requested user."""


class FocusConflictError(RuntimeError):
    """Raised when the requested focus action conflicts with session state."""


class FocusValidationError(ValueError):
    """Raised when focus input is invalid."""


class FocusPersistenceError(RuntimeError):
    """Raised when a focus database operation fails."""


@dataclass(frozen=True)
class FocusPageData:
    tasks: list[Task]
    active_session: FocusSession | None
    elapsed_seconds: int
    today_minutes: int


def clamp_integer(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def get_owned_task(task_id: Any, owner_id: int) -> Task | None:
    if not task_id:
        return None
    try:
        task_id = int(task_id)
    except (TypeError, ValueError):
        return None
    return Task.query.filter_by(id=task_id, user_id=owner_id).first()


def get_active_session(owner_id: int) -> FocusSession | None:
    return (
        FocusSession.query.filter_by(user_id=owner_id)
        .filter(FocusSession.status.in_(["running", "paused"]))
        .order_by(FocusSession.created_at.desc())
        .first()
    )


def require_owned_session(session_id: int, owner_id: int) -> FocusSession:
    session = FocusSession.query.filter_by(
        id=session_id,
        user_id=owner_id,
    ).first()
    if session is None:
        raise FocusNotFoundError
    return session


def require_owned_distraction(
    distraction_id: int,
    owner_id: int,
) -> FocusDistraction:
    distraction = FocusDistraction.query.filter_by(
        id=distraction_id,
        user_id=owner_id,
    ).first()
    if distraction is None:
        raise FocusNotFoundError
    return distraction


def current_elapsed_seconds(session: FocusSession) -> int:
    elapsed = session.elapsed_seconds or 0
    if session.status == "running" and session.started_at:
        elapsed += max(
            0,
            int((datetime.utcnow() - session.started_at).total_seconds()),
        )
    return elapsed


def get_focus_page_data(owner_id: int) -> FocusPageData:
    tasks = (
        Task.query.filter_by(user_id=owner_id)
        .filter(Task.status.notin_(["Completed", "Blocked"]))
        .order_by(Task.deadline.asc(), Task.priority_score.desc())
        .all()
    )
    session = get_active_session(owner_id)
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_sessions = FocusSession.query.filter(
        FocusSession.user_id == owner_id,
        FocusSession.completed_at >= today_start,
        FocusSession.status == "completed",
    ).all()
    return FocusPageData(
        tasks=tasks,
        active_session=session,
        elapsed_seconds=current_elapsed_seconds(session) if session else 0,
        today_minutes=sum(item.actual_minutes or 0 for item in today_sessions),
    )


def get_focus_insights(owner_id: int) -> dict[str, Any]:
    now = datetime.utcnow()
    seven_days_ago = datetime.combine(
        date.today() - timedelta(days=6),
        datetime.min.time(),
    )
    completed = (
        FocusSession.query.filter(
            FocusSession.user_id == owner_id,
            FocusSession.status == "completed",
        )
        .order_by(FocusSession.completed_at.desc())
        .all()
    )
    weekly_sessions = [
        item
        for item in completed
        if item.completed_at and item.completed_at >= seven_days_ago
    ]
    week_minutes = sum(item.actual_minutes or 0 for item in weekly_sessions)
    week_distractions = sum(
        item.distraction_count or 0 for item in weekly_sessions
    )
    rated = [item.focus_rating for item in weekly_sessions if item.focus_rating]
    average_rating = round(sum(rated) / len(rated), 1) if rated else None

    by_day: dict[date, int] = defaultdict(int)
    for item in weekly_sessions:
        by_day[item.completed_at.date()] += item.actual_minutes or 0

    max_minutes = max(by_day.values(), default=0)
    daily_data = []
    for offset in range(7):
        day = date.today() - timedelta(days=6 - offset)
        minutes = by_day.get(day, 0)
        daily_data.append(
            {
                "label": day.strftime("%a"),
                "date": day.strftime("%d %b"),
                "minutes": minutes,
                "height": round((minutes / max_minutes) * 100)
                if max_minutes
                else 0,
            }
        )

    project_totals: dict[str, int] = defaultdict(int)
    for item in completed:
        label = (
            item.task.project.title
            if item.task and item.task.project
            else "General workspace"
        )
        project_totals[label] += item.actual_minutes or 0

    project_data = sorted(
        (
            {"name": name, "minutes": minutes}
            for name, minutes in project_totals.items()
        ),
        key=lambda row: row["minutes"],
        reverse=True,
    )[:5]

    return {
        "week_minutes": week_minutes,
        "week_sessions": len(weekly_sessions),
        "week_distractions": week_distractions,
        "average_rating": average_rating,
        "daily_data": daily_data,
        "project_data": project_data,
        "recent_sessions": completed[:12],
        "generated_at": now,
    }


def _commit() -> None:
    try:
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise FocusPersistenceError from error


def start_session(
    owner_id: int,
    task_id: Any,
    duration_value: Any,
    goal_value: Any,
) -> FocusSession:
    if get_active_session(owner_id):
        raise FocusConflictError(
            "Finish or cancel the active focus session first."
        )
    task = get_owned_task(task_id, owner_id)
    duration = clamp_integer(duration_value, 25, 5, 180)
    goal = str(goal_value or "").strip()[:500] or None
    session = FocusSession(
        user_id=owner_id,
        task_id=task.id if task else None,
        title=task.title if task else "General focus session",
        goal=goal,
        planned_minutes=duration,
        status="running",
        started_at=datetime.utcnow(),
    )
    if task and task.status == "Pending":
        task.status = "In Progress"
    try:
        db.session.add(session)
        db.session.commit()
        return session
    except SQLAlchemyError as error:
        db.session.rollback()
        raise FocusPersistenceError from error


def pause_session(session: FocusSession) -> FocusSession:
    if session.status == "running":
        session.elapsed_seconds = current_elapsed_seconds(session)
        session.started_at = None
        session.status = "paused"
        _commit()
    return session


def resume_session(session: FocusSession) -> FocusSession:
    if session.status == "paused":
        session.started_at = datetime.utcnow()
        session.status = "running"
        _commit()
    return session


def extend_session(session: FocusSession) -> FocusSession:
    if session.status not in ("running", "paused"):
        raise FocusConflictError("This session is no longer active.")
    session.planned_minutes = min((session.planned_minutes or 25) + 5, 240)
    _commit()
    return session


def add_distraction(
    session: FocusSession,
    owner_id: int,
    content_value: Any,
) -> FocusDistraction:
    if session.status not in ("running", "paused"):
        raise FocusConflictError("This session is no longer active.")
    content = str(content_value or "").strip()
    if not content:
        raise FocusValidationError("Write a thought first.")
    thought = FocusDistraction(
        session_id=session.id,
        user_id=owner_id,
        content=content[:500],
    )
    session.distraction_count = (session.distraction_count or 0) + 1
    try:
        db.session.add(thought)
        db.session.commit()
        return thought
    except SQLAlchemyError as error:
        db.session.rollback()
        raise FocusPersistenceError from error


def convert_distraction_to_task(
    distraction: FocusDistraction,
    owner_id: int,
) -> tuple[Task, bool]:
    if distraction.converted_task_id:
        task = Task.query.filter_by(
            id=distraction.converted_task_id,
            user_id=owner_id,
        ).first()
        if task is not None:
            return task, True
    task = Task(
        user_id=owner_id,
        project_id=None,
        title=distraction.content[:200],
        description="Captured from the Focus Mode distraction inbox.",
        importance="Medium",
        difficulty="Low",
        status="Pending",
        priority_score=0,
    )
    try:
        db.session.add(task)
        db.session.flush()
        distraction.converted_task_id = task.id
        db.session.commit()
        return task, False
    except SQLAlchemyError as error:
        db.session.rollback()
        raise FocusPersistenceError from error


def begin_review(session: FocusSession) -> FocusSession:
    return pause_session(session)


def finish_session(
    session: FocusSession,
    notes_value: Any,
    goal_result_value: Any,
    focus_rating_value: Any,
    complete_task: bool,
) -> FocusSession:
    elapsed = current_elapsed_seconds(session)
    session.elapsed_seconds = elapsed
    session.actual_minutes = max(1, round(elapsed / 60)) if elapsed else 0
    session.status = "completed"
    session.completed_at = datetime.utcnow()
    session.started_at = None
    session.notes = str(notes_value or "").strip()[:2000] or None
    session.goal_result = (
        goal_result_value
        if goal_result_value in {"full", "partial", "not_yet"}
        else None
    )
    rating = clamp_integer(focus_rating_value, 0, 0, 5)
    session.focus_rating = rating or None
    if session.task and complete_task:
        session.task.status = "Completed"
        session.task.completed_at = datetime.utcnow()
        generate_next_occurrence(session.task)
    _commit()
    return session


def cancel_session(session: FocusSession) -> FocusSession:
    session.status = "cancelled"
    session.elapsed_seconds = current_elapsed_seconds(session)
    session.actual_minutes = round((session.elapsed_seconds or 0) / 60)
    session.completed_at = datetime.utcnow()
    session.started_at = None
    _commit()
    return session

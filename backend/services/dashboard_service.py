"""Shared dashboard query and serialization logic.

Both the legacy Flask/Jinja dashboard and the React API consume this service.
Keeping one authoritative calculation path prevents the two frontends from
quietly disagreeing while the React migration is in progress.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from models import Document, Note, Project, Task


_IMPORTANCE_ORDER = {
    "Critical": 4,
    "High": 3,
    "Medium": 2,
    "Low": 1,
}


def build_dashboard_context(owner_id: int) -> dict[str, Any]:
    """Return the canonical dashboard context for one user."""

    projects = (
        Project.query
        .filter_by(user_id=owner_id)
        .order_by(Project.created_at.desc())
        .all()
    )

    tasks = Task.query.filter_by(user_id=owner_id).all()

    projects_count = len(projects)
    tasks_count = len(tasks)

    general_tasks_count = sum(
        1 for task in tasks if task.project_id is None
    )
    project_tasks_count = tasks_count - general_tasks_count

    active_projects_count = sum(
        1
        for project in projects
        if project.status not in ("Completed", "Paused")
    )

    completed_tasks_count = sum(
        1 for task in tasks if task.status == "Completed"
    )
    blocked_tasks_count = sum(
        1 for task in tasks if task.status == "Blocked"
    )
    open_tasks_count = sum(
        1 for task in tasks if task.status != "Completed"
    )
    overdue_tasks_count = sum(
        1
        for task in tasks
        if (
            task.deadline
            and task.deadline < date.today()
            and task.status != "Completed"
        )
    )

    completion_rate = 0
    if tasks_count:
        completion_rate = round(
            completed_tasks_count / tasks_count * 100
        )

    average_project_progress = 0
    if projects_count:
        average_project_progress = round(
            sum(project.progress or 0 for project in projects)
            / projects_count
        )

    focus_candidates = [
        task
        for task in tasks
        if task.status not in ("Completed", "Blocked")
    ]

    def focus_sort_key(task: Task):
        status_rank = 0 if task.status == "In Progress" else 1
        deadline_rank = task.deadline or date.max

        return (
            status_rank,
            -_IMPORTANCE_ORDER.get(task.importance, 0),
            deadline_rank,
            -(task.priority_score or 0),
        )

    focus_task = None
    if focus_candidates:
        focus_task = sorted(
            focus_candidates,
            key=focus_sort_key,
        )[0]

    upcoming_tasks = sorted(
        [
            task
            for task in tasks
            if task.deadline and task.status != "Completed"
        ],
        key=lambda task: task.deadline,
    )[:5]

    latest_projects = projects[:4]

    notes_count = Note.query.filter_by(user_id=owner_id).count()

    documents_count = (
        Document.query
        .join(Project, Document.project_id == Project.id)
        .filter(Project.user_id == owner_id)
        .count()
    )

    return {
        "today": date.today(),
        "projects_count": projects_count,
        "active_projects_count": active_projects_count,
        "tasks_count": tasks_count,
        "general_tasks_count": general_tasks_count,
        "project_tasks_count": project_tasks_count,
        "open_tasks_count": open_tasks_count,
        "completed_tasks_count": completed_tasks_count,
        "blocked_tasks_count": blocked_tasks_count,
        "overdue_tasks_count": overdue_tasks_count,
        "completion_rate": completion_rate,
        "average_project_progress": average_project_progress,
        "notes_count": notes_count,
        "documents_count": documents_count,
        "focus_task": focus_task,
        "upcoming_tasks": upcoming_tasks,
        "latest_projects": latest_projects,
    }


def serialize_dashboard_context(
    context: dict[str, Any],
) -> dict[str, Any]:
    """Convert the canonical dashboard context into a JSON-safe API payload."""

    return {
        "today": context["today"].isoformat(),
        "counts": {
            "projects": context["projects_count"],
            "active_projects": context["active_projects_count"],
            "tasks": context["tasks_count"],
            "general_tasks": context["general_tasks_count"],
            "project_tasks": context["project_tasks_count"],
            "open_tasks": context["open_tasks_count"],
            "completed_tasks": context["completed_tasks_count"],
            "blocked_tasks": context["blocked_tasks_count"],
            "overdue_tasks": context["overdue_tasks_count"],
            "notes": context["notes_count"],
            "documents": context["documents_count"],
        },
        "completion_rate": context["completion_rate"],
        "average_project_progress": context[
            "average_project_progress"
        ],
        "focus_task": _serialize_task(
            context.get("focus_task")
        ),
        "upcoming_tasks": [
            _serialize_task(task)
            for task in context.get("upcoming_tasks", [])
        ],
        "latest_projects": [
            _serialize_project(project)
            for project in context.get("latest_projects", [])
        ],
    }


def _serialize_task(task: Task | None) -> dict[str, Any] | None:
    if task is None:
        return None

    project = task.project if task.project_id else None

    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "importance": task.importance,
        "module": task.module,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "priority_score": task.priority_score,
        "project": (
            {
                "id": project.id,
                "title": project.title,
            }
            if project is not None
            else None
        ),
    }


def _serialize_project(project: Project) -> dict[str, Any]:
    return {
        "id": project.id,
        "title": project.title,
        "status": project.status,
        "priority": project.priority,
        "progress": project.progress or 0,
        "current_phase": project.current_phase,
        "project_type": project.project_type,
        "deadline": (
            project.deadline.isoformat()
            if project.deadline
            else None
        ),
    }

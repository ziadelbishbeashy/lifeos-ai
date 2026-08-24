"""Landing page and Today's Workspace routes.

The routes are registered with their original endpoint names (``landing`` and
``dashboard``) so existing templates and redirects continue to work.
"""

from datetime import date

from flask import redirect, render_template, url_for
from flask_login import current_user, login_required

from models import Document, Note, Project, Task
from services.system_health_service import database_is_ready


def landing():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    return render_template("landing.html")


@login_required
def dashboard():
    projects = (
        Project.query
        .filter_by(user_id=current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )

    tasks = Task.query.filter_by(user_id=current_user.id).all()

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

    importance_order = {
        "Critical": 4,
        "High": 3,
        "Medium": 2,
        "Low": 1,
    }

    focus_candidates = [
        task
        for task in tasks
        if task.status not in ("Completed", "Blocked")
    ]

    def focus_sort_key(task):
        status_rank = 0 if task.status == "In Progress" else 1
        deadline_rank = task.deadline or date.max

        return (
            status_rank,
            -importance_order.get(task.importance, 0),
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

    notes_count = Note.query.filter_by(user_id=current_user.id).count()

    documents_count = (
        Document.query
        .join(Project, Document.project_id == Project.id)
        .filter(Project.user_id == current_user.id)
        .count()
    )

    return render_template(
        "dashboard.html",
        today=date.today(),
        projects_count=projects_count,
        active_projects_count=active_projects_count,
        tasks_count=tasks_count,
        general_tasks_count=general_tasks_count,
        project_tasks_count=project_tasks_count,
        open_tasks_count=open_tasks_count,
        completed_tasks_count=completed_tasks_count,
        blocked_tasks_count=blocked_tasks_count,
        overdue_tasks_count=overdue_tasks_count,
        completion_rate=completion_rate,
        average_project_progress=average_project_progress,
        notes_count=notes_count,
        documents_count=documents_count,
        focus_task=focus_task,
        upcoming_tasks=upcoming_tasks,
        latest_projects=latest_projects,
    )


def health():
    """Lightweight liveness check that does not touch external services."""

    return {"status": "ok", "service": "lifeos"}, 200


def readiness():
    """Readiness check used by deployment slots and container health probes."""

    ready = database_is_ready()
    return (
        {
            "status": "ready" if ready else "not_ready",
            "service": "lifeos",
            "database": "ok" if ready else "unavailable",
        },
        200 if ready else 503,
    )


def register_dashboard_routes(app) -> None:
    app.add_url_rule("/", endpoint="landing", view_func=landing)
    app.add_url_rule(
        "/dashboard",
        endpoint="dashboard",
        view_func=dashboard,
    )
    app.add_url_rule("/health", endpoint="health", view_func=health)
    app.add_url_rule(
        "/health/ready",
        endpoint="readiness",
        view_func=readiness,
    )

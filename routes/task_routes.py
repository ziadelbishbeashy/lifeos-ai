from datetime import date, datetime, timedelta 
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for
)
from flask_login import current_user, login_required

from database import db
from models import Project, Task


task_bp = Blueprint("task_bp", __name__)
@task_bp.route("/tasks")
@login_required
def all_tasks():
    tasks = (
        Task.query
        .join(Project)
        .filter(
            Project.user_id == current_user.id
        )
        .order_by(
            Task.created_at.desc()
        )
        .all()
    )

    today = date.today()
    upcoming_limit = today + timedelta(days=7)

    total_tasks = len(tasks)

    completed_tasks = sum(
        1
        for task in tasks
        if task.status == "Completed"
    )

    pending_tasks = sum(
        1
        for task in tasks
        if task.status == "Pending"
    )

    in_progress_tasks = sum(
        1
        for task in tasks
        if task.status == "In Progress"
    )

    blocked_tasks = sum(
        1
        for task in tasks
        if task.status == "Blocked"
    )

    overdue_tasks = [
        task
        for task in tasks
        if (
            task.deadline
            and task.deadline < today
            and task.status != "Completed"
        )
    ]

    due_soon_tasks = [
        task
        for task in tasks
        if (
            task.deadline
            and today <= task.deadline <= upcoming_limit
            and task.status != "Completed"
        )
    ]

    projects = (
        Project.query
        .filter_by(
            user_id=current_user.id
        )
        .order_by(
            Project.title.asc()
        )
        .all()
    )

    module_names = sorted(
        {
            task.module
            for task in tasks
            if task.module
        }
    )

    return render_template(
        "tasks.html",
        tasks=tasks,
        projects=projects,
        module_names=module_names,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        pending_tasks=pending_tasks,
        in_progress_tasks=in_progress_tasks,
        blocked_tasks=blocked_tasks,
        overdue_tasks=overdue_tasks,
        due_soon_tasks=due_soon_tasks,
        overdue_task_ids=[
            task.id
            for task in overdue_tasks
        ],
        due_soon_task_ids=[
            task.id
            for task in due_soon_tasks
        ]
    )

@task_bp.before_request
@login_required
def protect_task_routes():
    return None


def get_owned_project_or_404(project_id):
    return (
        Project.query
        .filter_by(
            id=project_id,
            user_id=current_user.id
        )
        .first_or_404()
    )


def get_owned_task_or_404(task_id):
    return (
        Task.query
        .join(Project)
        .filter(
            Task.id == task_id,
            Project.user_id == current_user.id
        )
        .first_or_404()
    )


def parse_date(value):
    if not value:
        return None

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d"
        ).date()
    except ValueError:
        return None


def clean_optional_text(value):
    if value is None:
        return None

    value = value.strip()
    return value if value else None


@task_bp.route(
    "/projects/<int:project_id>/tasks/add",
    methods=["POST"]
)
def add_task(project_id):
    project = get_owned_project_or_404(project_id)

    title = request.form.get("title", "").strip()

    if not title:
        flash("Task title is required.", "error")

        return redirect(
            url_for(
                "project_bp.project_details",
                project_id=project.id
            )
        )

    task = Task(
        project_id=project.id,
        title=title,
        description=clean_optional_text(
            request.form.get("description")
        ),
        module=clean_optional_text(
            request.form.get("module")
        ),
        importance=request.form.get(
            "importance",
            "Medium"
        ),
        difficulty=request.form.get(
            "difficulty",
            "Medium"
        ),
        deadline=parse_date(
            request.form.get("deadline")
        ),
        status=request.form.get(
            "status",
            "Pending"
        )
    )

    try:
        db.session.add(task)
        db.session.commit()

        flash(
            f'Task "{task.title}" added successfully.',
            "success"
        )
    except Exception as error:
        db.session.rollback()
        print("Add task error:", error)
        flash(
            "The task could not be saved.",
            "error"
        )

    return redirect(
        url_for(
            "project_bp.project_details",
            project_id=project.id
        )
    )


@task_bp.route(
    "/tasks/<int:task_id>/edit",
    methods=["GET", "POST"]
)
def edit_task(task_id):
    task = get_owned_task_or_404(task_id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()

        if not title:
            flash("Task title is required.", "error")

            return redirect(
                url_for(
                    "task_bp.edit_task",
                    task_id=task.id
                )
            )

        task.title = title
        task.description = clean_optional_text(
            request.form.get("description")
        )
        task.module = clean_optional_text(
            request.form.get("module")
        )
        task.importance = request.form.get(
            "importance",
            "Medium"
        )
        task.difficulty = request.form.get(
            "difficulty",
            "Medium"
        )
        task.deadline = parse_date(
            request.form.get("deadline")
        )
        task.status = request.form.get(
            "status",
            "Pending"
        )

        try:
            db.session.commit()
            flash(
                f'Task "{task.title}" updated successfully.',
                "success"
            )
        except Exception as error:
            db.session.rollback()
            print("Edit task error:", error)
            flash(
                "The task could not be updated.",
                "error"
            )

        return redirect(
            url_for(
                "project_bp.project_details",
                project_id=task.project_id
            )
        )

    return render_template(
        "edit_task.html",
        task=task
    )


@task_bp.route(
    "/tasks/<int:task_id>/toggle",
    methods=["POST"]
)
def toggle_task(task_id):
    task = get_owned_task_or_404(task_id)

    if task.status == "Completed":
        task.status = "Pending"
        message = f'Task "{task.title}" reopened.'
    else:
        task.status = "Completed"
        message = f'Task "{task.title}" completed.'

    try:
        db.session.commit()
        flash(message, "success")
    except Exception as error:
        db.session.rollback()
        print("Toggle task error:", error)
        flash(
            "The task status could not be updated.",
            "error"
        )

    return redirect(
        url_for(
            "project_bp.project_details",
            project_id=task.project_id
        )
    )


@task_bp.route(
    "/tasks/<int:task_id>/delete",
    methods=["POST"]
)
def delete_task(task_id):
    task = get_owned_task_or_404(task_id)

    project_id = task.project_id
    task_title = task.title

    try:
        db.session.delete(task)
        db.session.commit()

        flash(
            f'Task "{task_title}" deleted.',
            "success"
        )
    except Exception as error:
        db.session.rollback()
        print("Delete task error:", error)
        flash(
            "The task could not be deleted.",
            "error"
        )

    return redirect(
        url_for(
            "project_bp.project_details",
            project_id=project_id
        )
    )

from datetime import date, datetime, timedelta

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from database import db
from models import Project, Task


task_bp = Blueprint("task_bp", __name__)


@task_bp.before_request
@login_required
def protect_task_routes():
    return None


def parse_date(value):
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def clean_optional_text(value):
    if value is None:
        return None

    value = value.strip()
    return value if value else None


def get_owned_project_or_404(project_id):
    return (
        Project.query
        .filter_by(id=project_id, user_id=current_user.id)
        .first_or_404()
    )


def get_owned_task_or_404(task_id):
    return (
        Task.query
        .filter_by(id=task_id, user_id=current_user.id)
        .first_or_404()
    )


def get_task_fields_from_form(form):
    return {
        "title": form.get("title", "").strip(),
        "description": clean_optional_text(form.get("description")),
        "module": clean_optional_text(form.get("module")),
        "importance": form.get("importance", "Medium"),
        "difficulty": form.get("difficulty", "Medium"),
        "deadline": parse_date(form.get("deadline")),
        "status": form.get("status", "Pending"),
    }


def resolve_project_from_task_scope(form):
    """
    Return the selected Project for a project task.
    Return None when the task is a General Workspace Task.
    """

    scope = form.get("task_scope", "general")

    if scope != "project":
        return None

    project_id = form.get("project_id")

    if not project_id:
        raise ValueError("A project must be selected for project tasks.")

    try:
        project_id = int(project_id)
    except (TypeError, ValueError):
        raise ValueError("Invalid project selected.")

    project = (
        Project.query
        .filter_by(id=project_id, user_id=current_user.id)
        .first()
    )

    if not project:
        raise ValueError("Invalid project selected.")

    return project


def redirect_after_task_action(project_id=None):
    """
    Return the user to the page where the action happened.
    Global task actions return to the Tasks page.
    Project task actions return to the Project Details page.
    """

    next_page = request.form.get("next") or request.args.get("next")

    if next_page == "tasks":
        return redirect(url_for("task_bp.all_tasks"))

    if project_id:
        return redirect(
            url_for(
                "project_bp.project_details",
                project_id=project_id,
            )
        )

    return redirect(url_for("task_bp.all_tasks"))


@task_bp.route("/tasks")
def all_tasks():
    tasks = (
        Task.query
        .filter_by(user_id=current_user.id)
        .order_by(Task.created_at.desc())
        .all()
    )

    today = date.today()
    upcoming_limit = today + timedelta(days=7)

    total_tasks = len(tasks)

    completed_tasks = sum(
        1 for task in tasks if task.status == "Completed"
    )

    pending_tasks = sum(
        1 for task in tasks if task.status == "Pending"
    )

    in_progress_tasks = sum(
        1 for task in tasks if task.status == "In Progress"
    )

    blocked_tasks = sum(
        1 for task in tasks if task.status == "Blocked"
    )

    general_tasks_count = sum(
        1 for task in tasks if task.project_id is None
    )

    project_tasks_count = total_tasks - general_tasks_count

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
        .filter_by(user_id=current_user.id)
        .order_by(Project.title.asc())
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
        general_tasks_count=general_tasks_count,
        project_tasks_count=project_tasks_count,
        overdue_tasks=overdue_tasks,
        due_soon_tasks=due_soon_tasks,
        overdue_task_ids=[task.id for task in overdue_tasks],
        due_soon_task_ids=[task.id for task in due_soon_tasks],
    )


@task_bp.route("/tasks/add", methods=["POST"], endpoint="add_workspace_task")
def add_workspace_task():
    """
    Create a task from the global Tasks page.
    It can be either:
    - General Workspace Task: project_id = None
    - Project Task: project_id = selected project id
    """

    task_data = get_task_fields_from_form(request.form)

    if not task_data["title"]:
        flash("Task title is required.", "error")
        return redirect(url_for("task_bp.all_tasks"))

    try:
        project = resolve_project_from_task_scope(request.form)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("task_bp.all_tasks"))

    task = Task(
        user_id=current_user.id,
        project_id=project.id if project else None,
        **task_data,
    )

    try:
        db.session.add(task)
        db.session.commit()

        if project:
            flash(
                f'Task "{task.title}" added to "{project.title}".',
                "success",
            )
        else:
            flash(
                f'General task "{task.title}" added successfully.',
                "success",
            )

    except Exception as error:
        db.session.rollback()
        print("Add workspace task error:", error)
        flash("The task could not be saved.", "error")

    return redirect(url_for("task_bp.all_tasks"))


@task_bp.route("/projects/<int:project_id>/tasks/add", methods=["POST"])
def add_task(project_id):
    """
    Create a task from inside a project details page.
    This always creates a project task.
    """

    project = get_owned_project_or_404(project_id)
    task_data = get_task_fields_from_form(request.form)

    if not task_data["title"]:
        flash("Task title is required.", "error")
        return redirect(
            url_for(
                "project_bp.project_details",
                project_id=project.id,
            )
        )

    task = Task(
        user_id=current_user.id,
        project_id=project.id,
        **task_data,
    )

    try:
        db.session.add(task)
        db.session.commit()
        flash(f'Task "{task.title}" added successfully.', "success")

    except Exception as error:
        db.session.rollback()
        print("Add task error:", error)
        flash("The task could not be saved.", "error")

    return redirect(
        url_for(
            "project_bp.project_details",
            project_id=project.id,
        )
    )


@task_bp.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
def edit_task(task_id):
    task = get_owned_task_or_404(task_id)

    if request.method == "POST":
        task_data = get_task_fields_from_form(request.form)

        if not task_data["title"]:
            flash("Task title is required.", "error")
            return redirect(url_for("task_bp.edit_task", task_id=task.id))

        try:
            project = resolve_project_from_task_scope(request.form)
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("task_bp.edit_task", task_id=task.id))

        task.user_id = current_user.id
        task.project_id = project.id if project else None

        for field_name, field_value in task_data.items():
            setattr(task, field_name, field_value)

        try:
            db.session.commit()
            flash(f'Task "{task.title}" updated successfully.', "success")

        except Exception as error:
            db.session.rollback()
            print("Edit task error:", error)
            flash("The task could not be updated.", "error")

        return redirect_after_task_action(task.project_id)

    projects = (
        Project.query
        .filter_by(user_id=current_user.id)
        .order_by(Project.title.asc())
        .all()
    )

    return render_template(
        "edit_task.html",
        task=task,
        projects=projects,
    )


@task_bp.route("/tasks/<int:task_id>/toggle", methods=["POST"])
def toggle_task(task_id):
    task = get_owned_task_or_404(task_id)

    if task.status == "Completed":
        task.status = "Pending"
        message = f'Task "{task.title}" reopened.'
    else:
        task.status = "Completed"
        message = f'Task "{task.title}" completed.'

    project_id = task.project_id

    try:
        db.session.commit()
        flash(message, "success")

    except Exception as error:
        db.session.rollback()
        print("Toggle task error:", error)
        flash("The task status could not be updated.", "error")

    return redirect_after_task_action(project_id)


@task_bp.route("/tasks/<int:task_id>/delete", methods=["POST"])
def delete_task(task_id):
    task = get_owned_task_or_404(task_id)

    project_id = task.project_id
    task_title = task.title

    try:
        db.session.delete(task)
        db.session.commit()
        flash(f'Task "{task_title}" deleted.', "success")

    except Exception as error:
        db.session.rollback()
        print("Delete task error:", error)
        flash("The task could not be deleted.", "error")

    return redirect_after_task_action(project_id)

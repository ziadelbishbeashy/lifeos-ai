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
from services.recurring_task_service import calculate_next_date, generate_next_occurrence


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




def parse_time_value(value):
    if not value:
        return None

    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None


def combine_date_time(date_value, time_value):
    """
    Build an exact reminder datetime.

    Important: do not silently default to 09:00.
    The user must choose the reminder time from the form.
    """

    if not date_value or not time_value:
        return None

    return datetime.combine(date_value, time_value)


def build_reminder_datetime(form, deadline):
    reminder_enabled = form.get("reminder_enabled") == "on"

    if not reminder_enabled:
        return False, "none", None

    reminder_type = form.get("reminder_type") or "custom"

    # Backward compatibility with the previous 9:00 AM option name.
    if reminder_type == "due_morning":
        reminder_type = "due_time"

    reminder_time = parse_time_value(form.get("reminder_time"))

    if not reminder_time:
        raise ValueError("Please choose a reminder time.")

    if reminder_type == "custom":
        reminder_date = parse_date(form.get("reminder_date"))

        if not reminder_date:
            raise ValueError("Please choose a custom reminder date.")

        reminder_datetime = combine_date_time(reminder_date, reminder_time)

    else:
        if not deadline:
            raise ValueError(
                "Please set a task deadline before using deadline-based reminders."
            )

        reminder_datetime = combine_date_time(deadline, reminder_time)

        if reminder_type == "one_day_before":
            reminder_datetime = reminder_datetime - timedelta(days=1)

        elif reminder_type == "three_days_before":
            reminder_datetime = reminder_datetime - timedelta(days=3)

        elif reminder_type == "one_hour_before":
            reminder_datetime = reminder_datetime - timedelta(hours=1)

        elif reminder_type != "due_time":
            reminder_type = "custom"
            reminder_date = parse_date(form.get("reminder_date"))

            if not reminder_date:
                raise ValueError("Please choose a custom reminder date.")

            reminder_datetime = combine_date_time(reminder_date, reminder_time)

    if not reminder_datetime:
        raise ValueError(
            "Reminder is enabled, but no valid reminder time could be created."
        )

    return True, reminder_type, reminder_datetime

def build_recurrence_fields(form, deadline):
    is_recurring = form.get("is_recurring") == "on"

    if not is_recurring:
        return {
            "is_recurring": False,
            "recurrence_type": "none",
            "recurrence_interval": 1,
            "recurrence_end_date": None,
            "next_occurrence_date": None,
        }

    recurrence_type = form.get("recurrence_type", "daily")
    if recurrence_type not in {"daily", "weekly", "monthly", "custom_days"}:
        raise ValueError("Please choose a valid repeat pattern.")

    try:
        recurrence_interval = max(int(form.get("recurrence_interval", 1)), 1)
    except (TypeError, ValueError):
        raise ValueError("Repeat interval must be a positive number.")

    if recurrence_interval > 365:
        raise ValueError("Repeat interval is too large.")

    recurrence_end_date = parse_date(form.get("recurrence_end_date"))
    base_date = deadline or date.today()
    next_occurrence_date = calculate_next_date(
        base_date, recurrence_type, recurrence_interval
    )

    if recurrence_end_date and recurrence_end_date < next_occurrence_date:
        raise ValueError("Recurrence end date must allow at least one future occurrence.")

    return {
        "is_recurring": True,
        "recurrence_type": recurrence_type,
        "recurrence_interval": recurrence_interval,
        "recurrence_end_date": recurrence_end_date,
        "next_occurrence_date": next_occurrence_date,
    }


def clean_optional_text(value):
    if value is None:
        return None

    value = value.strip()
    return value if value else None


def sync_completed_at(task, previous_status=None):
    """Keep the analytics completion timestamp aligned with task status."""
    if task.status == "Completed":
        if previous_status != "Completed" or not task.completed_at:
            task.completed_at = datetime.utcnow()
    else:
        task.completed_at = None


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
    deadline = parse_date(form.get("deadline"))

    reminder_enabled, reminder_type, reminder_datetime = build_reminder_datetime(
        form,
        deadline,
    )

    recurrence_data = build_recurrence_fields(form, deadline)

    return {
        "title": form.get("title", "").strip(),
        "description": clean_optional_text(form.get("description")),
        "module": clean_optional_text(form.get("module")),
        "importance": form.get("importance", "Medium"),
        "difficulty": form.get("difficulty", "Medium"),
        "deadline": deadline,
        "status": form.get("status", "Pending"),
        "reminder_enabled": reminder_enabled,
        "reminder_type": reminder_type,
        "reminder_datetime": reminder_datetime,
        **recurrence_data,
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
    recurring_tasks_count = sum(1 for task in tasks if task.is_recurring)

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
        recurring_tasks_count=recurring_tasks_count,
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

    try:
        task_data = get_task_fields_from_form(request.form)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("task_bp.all_tasks"))

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
    sync_completed_at(task)

    try:
        db.session.add(task)
        db.session.flush()
        if task.is_recurring and not task.recurrence_series_id:
            task.recurrence_series_id = task.id
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

    try:
        task_data = get_task_fields_from_form(request.form)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(
            url_for(
                "project_bp.project_details",
                project_id=project.id,
            )
        )

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
    sync_completed_at(task)

    try:
        db.session.add(task)
        db.session.flush()
        if task.is_recurring and not task.recurrence_series_id:
            task.recurrence_series_id = task.id
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
        try:
            task_data = get_task_fields_from_form(request.form)
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("task_bp.edit_task", task_id=task.id))

        if not task_data["title"]:
            flash("Task title is required.", "error")
            return redirect(url_for("task_bp.edit_task", task_id=task.id))

        try:
            project = resolve_project_from_task_scope(request.form)
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("task_bp.edit_task", task_id=task.id))

        previous_status = task.status
        task.user_id = current_user.id
        task.project_id = project.id if project else None

        for field_name, field_value in task_data.items():
            setattr(task, field_name, field_value)

        sync_completed_at(task, previous_status)

        if task.is_recurring and not task.recurrence_series_id:
            task.recurrence_series_id = task.id

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
        task.completed_at = None
        message = f'Task "{task.title}" reopened.'
    else:
        task.status = "Completed"
        task.completed_at = datetime.utcnow()
        next_task = generate_next_occurrence(task)
        if next_task:
            message = (
                f'Task "{task.title}" completed. '
                f'Next occurrence created for {next_task.deadline.strftime("%d %b %Y")}.'
            )
        else:
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

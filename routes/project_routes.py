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


project_bp = Blueprint(
    "project_bp",
    __name__
)


# =====================================================
# Helper functions
# =====================================================

def parse_date(value):
    """
    Convert an HTML date value such as 2026-07-17
    into a Python date object.

    Empty or invalid values return None.
    """

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
    """
    Remove unnecessary spaces from optional text fields.

    Empty values are stored as None.
    """

    if value is None:
        return None

    cleaned_value = value.strip()

    return cleaned_value if cleaned_value else None


def parse_progress(value):
    """
    Convert progress into an integer between 0 and 100.
    """

    try:
        progress = int(value or 0)

    except (TypeError, ValueError):
        progress = 0

    return max(0, min(100, progress))


def project_fields_from_form(form):
    """
    Collect and clean all project form values.
    """

    no_deadline = (
        form.get("no_deadline") == "on"
    )

    deadline = None

    if not no_deadline:
        deadline = parse_date(
            form.get("deadline")
        )

    return {
        "title": form.get(
            "title",
            ""
        ).strip(),

        "project_type": clean_optional_text(
            form.get("project_type")
        ),

        "description": clean_optional_text(
            form.get("description")
        ),

        "goal": clean_optional_text(
            form.get("goal")
        ),

        "tech_stack": clean_optional_text(
            form.get("tech_stack")
        ),

        "project_folder": clean_optional_text(
            form.get("project_folder")
        ),

        "github_link": clean_optional_text(
            form.get("github_link")
        ),

        "demo_link": clean_optional_text(
            form.get("demo_link")
        ),

        "start_date": parse_date(
            form.get("start_date")
        ),

        "deadline": deadline,

        "status": form.get(
            "status",
            "In Progress"
        ),

        "priority": form.get(
            "priority",
            "Medium"
        ),

        "current_phase": clean_optional_text(
            form.get("current_phase")
        ),

        "progress": parse_progress(
            form.get("progress")
        )
    }


def get_owned_project_or_404(project_id):
    """
    Return a project only when it belongs to the
    currently logged-in user.
    """

    return (
        Project.query
        .filter_by(
            id=project_id,
            user_id=current_user.id
        )
        .first_or_404()
    )


# =====================================================
# Projects list and project creation
# =====================================================

@project_bp.route(
    "/projects",
    methods=["GET", "POST"]
)
@login_required
def projects():
    if request.method == "POST":
        project_data = project_fields_from_form(
            request.form
        )

        if not project_data["title"]:
            flash(
                "Project title is required.",
                "error"
            )

            return redirect(
                url_for(
                    "project_bp.projects"
                )
            )

        new_project = Project(
            user_id=current_user.id,
            **project_data
        )

        try:
            db.session.add(new_project)
            db.session.commit()

            flash(
                f'Project "{new_project.title}" '
                "created successfully.",
                "success"
            )

        except Exception as error:
            db.session.rollback()

            print(
                "Create project error:",
                error
            )

            flash(
                "The project could not be created.",
                "error"
            )

        return redirect(
            url_for(
                "project_bp.projects"
            )
        )

    all_projects = (
        Project.query
        .filter_by(
            user_id=current_user.id
        )
        .order_by(
            Project.created_at.desc()
        )
        .all()
    )

    return render_template(
        "projects.html",
        projects=all_projects
    )


# =====================================================
# Project workspace and Phase 3 task statistics
# =====================================================

@project_bp.route(
    "/projects/<int:project_id>"
)
@login_required
def project_details(project_id):
    project = get_owned_project_or_404(
        project_id
    )

    tasks = (
        Task.query
        .filter_by(
            project_id=project.id
        )
        .order_by(
            Task.created_at.desc()
        )
        .all()
    )

    # Used to sort tasks by importance.
    importance_order = {
        "Low": 1,
        "Medium": 2,
        "High": 3,
        "Critical": 4
    }

    # Sorting order:
    # 1. Uncompleted before completed
    # 2. Tasks with deadlines before tasks without deadlines
    # 3. Earlier deadlines first
    # 4. Higher importance first
    tasks.sort(
        key=lambda task: (
            task.status == "Completed",
            task.deadline is None,
            task.deadline or date.max,
            -importance_order.get(
                task.importance,
                0
            )
        )
    )

    today = date.today()

    upcoming_limit = (
        today + timedelta(days=7)
    )

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
            and today
            <= task.deadline
            <= upcoming_limit
            and task.status != "Completed"
        )
    ]

    high_priority_tasks = [
        task
        for task in tasks
        if (
            task.importance in (
                "High",
                "Critical"
            )
            and task.status != "Completed"
        )
    ]

    task_progress = 0

    if total_tasks > 0:
        task_progress = round(
            completed_tasks
            / total_tasks
            * 100
        )

    module_names = sorted(
        {
            task.module
            for task in tasks
            if task.module
        }
    )

    overdue_task_ids = [
        task.id
        for task in overdue_tasks
    ]

    due_soon_task_ids = [
        task.id
        for task in due_soon_tasks
    ]

    return render_template(
        "project_details.html",

        project=project,
        tasks=tasks,

        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        pending_tasks=pending_tasks,
        in_progress_tasks=in_progress_tasks,
        blocked_tasks=blocked_tasks,

        overdue_tasks=overdue_tasks,
        due_soon_tasks=due_soon_tasks,
        high_priority_tasks=high_priority_tasks,

        overdue_task_ids=overdue_task_ids,
        due_soon_task_ids=due_soon_task_ids,

        task_progress=task_progress,
        module_names=module_names
    )


# =====================================================
# Edit project
# =====================================================

@project_bp.route(
    "/projects/<int:project_id>/edit",
    methods=["GET", "POST"]
)
@login_required
def edit_project(project_id):
    project = get_owned_project_or_404(
        project_id
    )

    if request.method == "POST":
        project_data = project_fields_from_form(
            request.form
        )

        if not project_data["title"]:
            flash(
                "Project title is required.",
                "error"
            )

            return redirect(
                url_for(
                    "project_bp.edit_project",
                    project_id=project.id
                )
            )

        for field_name, field_value in (
            project_data.items()
        ):
            setattr(
                project,
                field_name,
                field_value
            )

        try:
            db.session.commit()

            flash(
                f'Project "{project.title}" '
                "updated successfully.",
                "success"
            )

        except Exception as error:
            db.session.rollback()

            print(
                "Edit project error:",
                error
            )

            flash(
                "The project could not be updated.",
                "error"
            )

            return redirect(
                url_for(
                    "project_bp.edit_project",
                    project_id=project.id
                )
            )

        return redirect(
            url_for(
                "project_bp.project_details",
                project_id=project.id
            )
        )

    return render_template(
        "edit_project.html",
        project=project
    )


# =====================================================
# Delete project
# =====================================================

@project_bp.route(
    "/projects/<int:project_id>/delete",
    methods=["POST"]
)
@login_required
def delete_project(project_id):
    project = get_owned_project_or_404(
        project_id
    )

    project_title = project.title

    try:
        db.session.delete(project)
        db.session.commit()

        flash(
            f'Project "{project_title}" deleted.',
            "success"
        )

    except Exception as error:
        db.session.rollback()

        print(
            "Delete project error:",
            error
        )

        flash(
            "The project could not be deleted.",
            "error"
        )

    return redirect(
        url_for(
            "project_bp.projects"
        )
    )
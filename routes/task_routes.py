"""HTTP routes for the LifeOS Tasks experience."""

from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from services.task_service import (
    TaskNotFoundError,
    TaskPersistenceError,
    TaskProjectNotFoundError,
    TaskValidationError,
    build_task_input,
    build_tasks_overview,
    create_task,
    delete_task as delete_task_record,
    list_owned_projects,
    require_owned_project,
    require_owned_task,
    toggle_task_completion,
    update_task,
)


task_bp = Blueprint("task_bp", __name__)


@task_bp.before_request
@login_required
def protect_task_routes():
    return None


def _owned_task_or_404(task_id: int):
    try:
        return require_owned_task(task_id, current_user.id)
    except TaskNotFoundError:
        abort(404)


def _owned_project_or_404(project_id: int):
    try:
        return require_owned_project(project_id, current_user.id)
    except TaskProjectNotFoundError:
        abort(404)


def redirect_after_task_action(project_id: int | None = None):
    """Return the user to the page where the task action happened."""

    next_page = request.form.get("next") or request.args.get("next")
    if next_page == "tasks":
        return redirect(url_for("task_bp.all_tasks"))

    if project_id:
        return redirect(
            url_for("project_bp.project_details", project_id=project_id)
        )

    return redirect(url_for("task_bp.all_tasks"))


@task_bp.route("/tasks")
def all_tasks():
    return render_template("tasks.html", **build_tasks_overview(current_user.id))


@task_bp.route("/tasks/add", methods=["POST"], endpoint="add_workspace_task")
def add_workspace_task():
    try:
        task_data = build_task_input(request.form, current_user.id)
        task = create_task(current_user.id, task_data)

        if task.project:
            flash(
                f'Task "{task.title}" added to "{task.project.title}".',
                "success",
            )
        else:
            flash(f'General task "{task.title}" added successfully.', "success")
    except TaskValidationError as error:
        flash(str(error), "error")
    except TaskProjectNotFoundError:
        flash("Invalid project selected.", "error")
    except TaskPersistenceError:
        current_app.logger.exception("LifeOS could not create a workspace task.")
        flash("The task could not be saved.", "error")

    return redirect(url_for("task_bp.all_tasks"))


@task_bp.route("/projects/<int:project_id>/tasks/add", methods=["POST"])
def add_task(project_id):
    project = _owned_project_or_404(project_id)

    try:
        task_data = build_task_input(
            request.form,
            current_user.id,
            forced_project_id=project.id,
        )
        task = create_task(current_user.id, task_data)
        flash(f'Task "{task.title}" added successfully.', "success")
    except TaskValidationError as error:
        flash(str(error), "error")
    except TaskProjectNotFoundError:
        abort(404)
    except TaskPersistenceError:
        current_app.logger.exception(
            "LifeOS could not create a task for project %s.",
            project.id,
        )
        flash("The task could not be saved.", "error")

    return redirect(
        url_for("project_bp.project_details", project_id=project.id)
    )


@task_bp.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
def edit_task(task_id):
    task = _owned_task_or_404(task_id)

    if request.method == "POST":
        try:
            task_data = build_task_input(request.form, current_user.id)
            task = update_task(task, task_data)
            flash(f'Task "{task.title}" updated successfully.', "success")
        except TaskValidationError as error:
            flash(str(error), "error")
            return redirect(url_for("task_bp.edit_task", task_id=task.id))
        except TaskProjectNotFoundError:
            flash("Invalid project selected.", "error")
            return redirect(url_for("task_bp.edit_task", task_id=task.id))
        except TaskPersistenceError:
            current_app.logger.exception(
                "LifeOS could not update task %s.",
                task.id,
            )
            flash("The task could not be updated.", "error")
            return redirect(url_for("task_bp.edit_task", task_id=task.id))

        return redirect_after_task_action(task.project_id)

    return render_template(
        "edit_task.html",
        task=task,
        projects=list_owned_projects(current_user.id),
    )


@task_bp.route("/tasks/<int:task_id>/toggle", methods=["POST"])
def toggle_task(task_id):
    task = _owned_task_or_404(task_id)

    try:
        result = toggle_task_completion(task)
        flash(result.message, "success")
        return redirect_after_task_action(result.project_id)
    except TaskPersistenceError:
        current_app.logger.exception(
            "LifeOS could not toggle task %s.",
            task.id,
        )
        flash("The task status could not be updated.", "error")
        return redirect_after_task_action(task.project_id)


@task_bp.route("/tasks/<int:task_id>/delete", methods=["POST"])
def delete_task(task_id):
    task = _owned_task_or_404(task_id)

    try:
        result = delete_task_record(task)
        flash(f'Task "{result.title}" deleted.', "success")
        return redirect_after_task_action(result.project_id)
    except TaskPersistenceError:
        current_app.logger.exception(
            "LifeOS could not delete task %s.",
            task.id,
        )
        flash("The task could not be deleted.", "error")
        return redirect_after_task_action(task.project_id)

"""React API for the user task workspace."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from flask_login import current_user

from lifeos.api.v1.common import (
    api_auth_required,
    json_body,
    not_found,
    persistence_error,
    validation_error,
)
from lifeos.api.v1.serializers import serialize_project_summary, serialize_task
from lifeos.domains.tasks.facade import (
    TaskNotFoundError,
    TaskPersistenceError,
    TaskProjectNotFoundError,
    TaskValidationError,
    build_task_input,
    build_tasks_overview,
    create_task,
    delete_task,
    require_owned_task,
    toggle_task_completion,
    update_task,
)


tasks_api_bp = Blueprint(
    "api_v1_tasks",
    __name__,
    url_prefix="/api/v1/tasks",
)


def _task_form(task=None) -> dict:
    if task is None:
        return {
            "task_scope": "general",
            "status": "Pending",
            "importance": "Medium",
            "difficulty": "Medium",
            "reminder_enabled": "",
            "is_recurring": "",
        }

    reminder_date = ""
    reminder_time = ""
    if task.reminder_datetime is not None:
        reminder_date = task.reminder_datetime.date().isoformat()
        reminder_time = task.reminder_datetime.time().strftime("%H:%M")

    return {
        "task_scope": "project" if task.project_id is not None else "general",
        "project_id": task.project_id or "",
        "title": task.title or "",
        "description": task.description or "",
        "module": task.module or "",
        "tags": task.tags or "",
        "importance": task.importance or "Medium",
        "difficulty": task.difficulty or "Medium",
        "deadline": task.deadline.isoformat() if task.deadline else "",
        "status": task.status or "Pending",
        "reminder_enabled": "on" if task.reminder_enabled else "",
        "reminder_type": task.reminder_type or "custom",
        "reminder_date": reminder_date,
        "reminder_time": reminder_time,
        "is_recurring": "on" if task.is_recurring else "",
        "recurrence_type": task.recurrence_type or "daily",
        "recurrence_interval": task.recurrence_interval or 1,
        "recurrence_end_date": (
            task.recurrence_end_date.isoformat()
            if task.recurrence_end_date
            else ""
        ),
    }


def _task_input_from_json(payload: dict, task=None, forced_project_id=None):
    form = _task_form(task)
    form.update(payload)

    project_id = form.get("project_id")
    if forced_project_id is not None:
        form["task_scope"] = "project"
        form["project_id"] = forced_project_id
    elif "project_id" in payload:
        form["task_scope"] = "project" if project_id not in (None, "") else "general"

    for field in ("reminder_enabled", "is_recurring"):
        if isinstance(form.get(field), bool):
            form[field] = "on" if form[field] else ""

    return build_task_input(
        form,
        current_user.id,
        forced_project_id=forced_project_id,
    )


@tasks_api_bp.get("")
@api_auth_required
def list_tasks():
    overview = build_tasks_overview(current_user.id)
    return jsonify(
        {
            "items": [serialize_task(task) for task in overview["tasks"]],
            "projects": [
                serialize_project_summary(project) for project in overview["projects"]
            ],
            "module_names": overview["module_names"],
            "counts": {
                "total": overview["total_tasks"],
                "completed": overview["completed_tasks"],
                "pending": overview["pending_tasks"],
                "in_progress": overview["in_progress_tasks"],
                "blocked": overview["blocked_tasks"],
                "general": overview["general_tasks_count"],
                "project": overview["project_tasks_count"],
                "recurring": overview["recurring_tasks_count"],
                "overdue": len(overview["overdue_tasks"]),
                "due_soon": len(overview["due_soon_tasks"]),
            },
        }
    )


@tasks_api_bp.post("")
@api_auth_required
def create_task_route():
    payload = json_body()
    forced_project_id = payload.pop("forced_project_id", None)
    try:
        task = create_task(
            current_user.id,
            _task_input_from_json(
                payload,
                forced_project_id=forced_project_id,
            ),
        )
    except TaskValidationError as error:
        return validation_error(str(error))
    except TaskProjectNotFoundError:
        return not_found("Project not found.")
    except TaskPersistenceError:
        current_app.logger.exception("LifeOS API could not create a task.")
        return persistence_error("The task could not be created.")

    return jsonify({"item": serialize_task(task)}), 201


@tasks_api_bp.get("/<int:task_id>")
@api_auth_required
def task_details_route(task_id: int):
    try:
        task = require_owned_task(task_id, current_user.id)
    except TaskNotFoundError:
        return not_found("Task not found.")
    return jsonify({"item": serialize_task(task)})


@tasks_api_bp.patch("/<int:task_id>")
@api_auth_required
def update_task_route(task_id: int):
    try:
        task = require_owned_task(task_id, current_user.id)
    except TaskNotFoundError:
        return not_found("Task not found.")

    try:
        updated = update_task(task, _task_input_from_json(json_body(), task=task))
    except TaskValidationError as error:
        return validation_error(str(error))
    except TaskProjectNotFoundError:
        return not_found("Project not found.")
    except TaskPersistenceError:
        current_app.logger.exception("LifeOS API could not update task %s.", task_id)
        return persistence_error("The task could not be updated.")

    return jsonify({"item": serialize_task(updated)})


@tasks_api_bp.post("/<int:task_id>/toggle")
@api_auth_required
def toggle_task_route(task_id: int):
    try:
        task = require_owned_task(task_id, current_user.id)
    except TaskNotFoundError:
        return not_found("Task not found.")

    try:
        result = toggle_task_completion(task)
    except TaskPersistenceError:
        current_app.logger.exception("LifeOS API could not toggle task %s.", task_id)
        return persistence_error("The task status could not be updated.")

    return jsonify({"item": serialize_task(result.task), "message": result.message})


@tasks_api_bp.delete("/<int:task_id>")
@api_auth_required
def delete_task_route(task_id: int):
    try:
        task = require_owned_task(task_id, current_user.id)
    except TaskNotFoundError:
        return not_found("Task not found.")

    try:
        result = delete_task(task)
    except TaskPersistenceError:
        current_app.logger.exception("LifeOS API could not delete task %s.", task_id)
        return persistence_error("The task could not be deleted.")

    return jsonify(
        {
            "deleted": True,
            "title": result.title,
            "project_id": result.project_id,
        }
    )

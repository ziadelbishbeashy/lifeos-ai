"""Task business rules and persistence for LifeOS.

Routes should handle HTTP concerns only. This module owns task form
normalisation, validation, ownership-safe queries, reminder and recurrence
rules, persistence, completion state, and factual overview data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Mapping

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import AITaskSuggestion, DocumentTaskSuggestion, Project, Task
from services.recurring_task_service import calculate_next_date, generate_next_occurrence


TASK_STATUSES = frozenset({"Pending", "In Progress", "Blocked", "Completed"})
TASK_IMPORTANCE_LEVELS = frozenset({"Low", "Medium", "High", "Critical"})
TASK_DIFFICULTY_LEVELS = frozenset({"Easy", "Medium", "Hard"})
RECURRENCE_TYPES = frozenset({"daily", "weekly", "monthly", "custom_days"})
REMINDER_TYPES = frozenset(
    {"custom", "due_time", "one_day_before", "three_days_before", "one_hour_before"}
)


class TaskValidationError(ValueError):
    """Raised when submitted task data is not valid."""


class TaskNotFoundError(LookupError):
    """Raised when a task does not exist for the requested owner."""


class TaskProjectNotFoundError(LookupError):
    """Raised when a selected project does not belong to the requested owner."""


class TaskPersistenceError(RuntimeError):
    """Raised when a database operation for a task cannot be completed."""


@dataclass(frozen=True)
class TaskInput:
    """Normalised values received from a task form."""

    project_id: int | None
    title: str
    description: str | None
    module: str | None
    tags: str | None
    importance: str
    difficulty: str
    deadline: date | None
    status: str
    reminder_enabled: bool
    reminder_type: str
    reminder_datetime: datetime | None
    is_recurring: bool
    recurrence_type: str
    recurrence_interval: int
    recurrence_end_date: date | None
    next_occurrence_date: date | None

    def as_model_fields(self) -> dict[str, Any]:
        """Return fields that can safely be assigned to a Task model."""

        return {
            "project_id": self.project_id,
            "title": self.title,
            "description": self.description,
            "module": self.module,
            "tags": self.tags,
            "importance": self.importance,
            "difficulty": self.difficulty,
            "deadline": self.deadline,
            "status": self.status,
            "reminder_enabled": self.reminder_enabled,
            "reminder_type": self.reminder_type,
            "reminder_datetime": self.reminder_datetime,
            "is_recurring": self.is_recurring,
            "recurrence_type": self.recurrence_type,
            "recurrence_interval": self.recurrence_interval,
            "recurrence_end_date": self.recurrence_end_date,
            "next_occurrence_date": self.next_occurrence_date,
        }


@dataclass(frozen=True)
class TaskToggleResult:
    """Outcome of changing a task's completion state."""

    task: Task
    message: str
    project_id: int | None


@dataclass(frozen=True)
class DeletedTaskResult:
    """Information needed after a task is deleted."""

    title: str
    project_id: int | None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None

    try:
        return datetime.strptime(value, "%H:%M").time()
    except (TypeError, ValueError):
        return None


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()
    return cleaned or None


def normalize_task_tags(value: str | None) -> str | None:
    """Normalize a comma-separated tag list without trusting raw form text."""

    if not value:
        return None

    tags: list[str] = []
    seen: set[str] = set()

    for raw_tag in str(value).replace(";", ",").split(","):
        tag = " ".join(raw_tag.strip().split())[:40]
        key = tag.casefold()

        if not tag or key in seen:
            continue

        seen.add(key)
        tags.append(tag)

        if len(tags) >= 12:
            break

    return ", ".join(tags) or None


def _resolve_project_id(
    form: Mapping[str, Any],
    owner_id: int,
    forced_project_id: int | None,
) -> int | None:
    """Resolve and ownership-check the selected task project."""

    if forced_project_id is not None:
        project_id = forced_project_id
    elif form.get("task_scope", "general") != "project":
        return None
    else:
        raw_project_id = form.get("project_id")
        if not raw_project_id:
            raise TaskValidationError("A project must be selected for project tasks.")

        try:
            project_id = int(raw_project_id)
        except (TypeError, ValueError) as error:
            raise TaskValidationError("Invalid project selected.") from error

    project = Project.query.filter_by(id=project_id, user_id=owner_id).first()
    if project is None:
        raise TaskProjectNotFoundError

    return project.id


def _build_reminder_fields(
    form: Mapping[str, Any],
    deadline: date | None,
) -> tuple[bool, str, datetime | None]:
    enabled = form.get("reminder_enabled") == "on"
    if not enabled:
        return False, "none", None

    reminder_type = (form.get("reminder_type") or "custom").strip()
    if reminder_type == "due_morning":
        reminder_type = "due_time"

    if reminder_type not in REMINDER_TYPES:
        raise TaskValidationError("Please choose a valid reminder type.")

    reminder_time = _parse_time(form.get("reminder_time"))
    if reminder_time is None:
        raise TaskValidationError("Please choose a reminder time.")

    if reminder_type == "custom":
        reminder_date = _parse_date(form.get("reminder_date"))
        if reminder_date is None:
            raise TaskValidationError("Please choose a custom reminder date.")
        reminder_datetime = datetime.combine(reminder_date, reminder_time)
    else:
        if deadline is None:
            raise TaskValidationError(
                "Please set a task deadline before using deadline-based reminders."
            )

        reminder_datetime = datetime.combine(deadline, reminder_time)
        if reminder_type == "one_day_before":
            reminder_datetime -= timedelta(days=1)
        elif reminder_type == "three_days_before":
            reminder_datetime -= timedelta(days=3)
        elif reminder_type == "one_hour_before":
            reminder_datetime -= timedelta(hours=1)

    return True, reminder_type, reminder_datetime


def _build_recurrence_fields(
    form: Mapping[str, Any],
    deadline: date | None,
) -> dict[str, Any]:
    is_recurring = form.get("is_recurring") == "on"
    if not is_recurring:
        return {
            "is_recurring": False,
            "recurrence_type": "none",
            "recurrence_interval": 1,
            "recurrence_end_date": None,
            "next_occurrence_date": None,
        }

    recurrence_type = (form.get("recurrence_type") or "daily").strip()
    if recurrence_type not in RECURRENCE_TYPES:
        raise TaskValidationError("Please choose a valid repeat pattern.")

    try:
        recurrence_interval = max(int(form.get("recurrence_interval") or 1), 1)
    except (TypeError, ValueError) as error:
        raise TaskValidationError("Repeat interval must be a positive number.") from error

    if recurrence_interval > 365:
        raise TaskValidationError("Repeat interval is too large.")

    recurrence_end_date = _parse_date(form.get("recurrence_end_date"))
    base_date = deadline or date.today()
    next_occurrence_date = calculate_next_date(
        base_date,
        recurrence_type,
        recurrence_interval,
    )

    if recurrence_end_date and recurrence_end_date < next_occurrence_date:
        raise TaskValidationError(
            "Recurrence end date must allow at least one future occurrence."
        )

    return {
        "is_recurring": True,
        "recurrence_type": recurrence_type,
        "recurrence_interval": recurrence_interval,
        "recurrence_end_date": recurrence_end_date,
        "next_occurrence_date": next_occurrence_date,
    }


def build_task_input(
    form: Mapping[str, Any],
    owner_id: int,
    *,
    forced_project_id: int | None = None,
) -> TaskInput:
    """Create a stable task input object from submitted form values."""

    project_id = _resolve_project_id(form, owner_id, forced_project_id)
    deadline = _parse_date(form.get("deadline"))
    reminder_enabled, reminder_type, reminder_datetime = _build_reminder_fields(
        form,
        deadline,
    )
    recurrence = _build_recurrence_fields(form, deadline)

    return TaskInput(
        project_id=project_id,
        title=(form.get("title") or "").strip(),
        description=_clean_optional_text(form.get("description")),
        module=_clean_optional_text(form.get("module")),
        tags=normalize_task_tags(form.get("tags")),
        importance=(form.get("importance") or "Medium").strip(),
        difficulty=(form.get("difficulty") or "Medium").strip(),
        deadline=deadline,
        status=(form.get("status") or "Pending").strip(),
        reminder_enabled=reminder_enabled,
        reminder_type=reminder_type,
        reminder_datetime=reminder_datetime,
        is_recurring=recurrence["is_recurring"],
        recurrence_type=recurrence["recurrence_type"],
        recurrence_interval=recurrence["recurrence_interval"],
        recurrence_end_date=recurrence["recurrence_end_date"],
        next_occurrence_date=recurrence["next_occurrence_date"],
    )


def validate_task_input(data: TaskInput) -> None:
    """Raise ``TaskValidationError`` when submitted task data is invalid."""

    if not data.title:
        raise TaskValidationError("Task title is required.")

    if len(data.title) > 200:
        raise TaskValidationError("Task title must contain 200 characters or fewer.")

    if data.status not in TASK_STATUSES:
        raise TaskValidationError("Please choose a valid task status.")

    if data.importance not in TASK_IMPORTANCE_LEVELS:
        raise TaskValidationError("Please choose a valid task importance.")

    if data.difficulty not in TASK_DIFFICULTY_LEVELS:
        raise TaskValidationError("Please choose a valid task difficulty.")


def _sync_completed_at(task: Task, previous_status: str | None = None) -> None:
    """Keep the analytics completion timestamp aligned with task status."""

    if task.status == "Completed":
        if previous_status != "Completed" or not task.completed_at:
            task.completed_at = datetime.utcnow()
    else:
        task.completed_at = None


def get_owned_task(task_id: int, owner_id: int) -> Task | None:
    """Return a task only when it belongs to the requested user."""

    return Task.query.filter_by(id=task_id, user_id=owner_id).first()


def require_owned_task(task_id: int, owner_id: int) -> Task:
    task = get_owned_task(task_id, owner_id)
    if task is None:
        raise TaskNotFoundError
    return task


def get_owned_project(project_id: int, owner_id: int) -> Project | None:
    return Project.query.filter_by(id=project_id, user_id=owner_id).first()


def require_owned_project(project_id: int, owner_id: int) -> Project:
    project = get_owned_project(project_id, owner_id)
    if project is None:
        raise TaskProjectNotFoundError
    return project


def list_owned_projects(owner_id: int) -> list[Project]:
    return (
        Project.query.filter_by(user_id=owner_id)
        .order_by(Project.title.asc())
        .all()
    )


def build_tasks_overview(owner_id: int) -> dict[str, Any]:
    """Return factual task-page data for one user workspace."""

    tasks = (
        Task.query.filter_by(user_id=owner_id)
        .order_by(Task.created_at.desc())
        .all()
    )
    today = date.today()
    upcoming_limit = today + timedelta(days=7)

    overdue_tasks = [
        task
        for task in tasks
        if task.deadline and task.deadline < today and task.status != "Completed"
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

    return {
        "tasks": tasks,
        "projects": list_owned_projects(owner_id),
        "module_names": sorted({task.module for task in tasks if task.module}),
        "total_tasks": len(tasks),
        "completed_tasks": sum(1 for task in tasks if task.status == "Completed"),
        "pending_tasks": sum(1 for task in tasks if task.status == "Pending"),
        "in_progress_tasks": sum(1 for task in tasks if task.status == "In Progress"),
        "blocked_tasks": sum(1 for task in tasks if task.status == "Blocked"),
        "general_tasks_count": sum(1 for task in tasks if task.project_id is None),
        "project_tasks_count": sum(1 for task in tasks if task.project_id is not None),
        "recurring_tasks_count": sum(1 for task in tasks if task.is_recurring),
        "overdue_tasks": overdue_tasks,
        "due_soon_tasks": due_soon_tasks,
        "overdue_task_ids": [task.id for task in overdue_tasks],
        "due_soon_task_ids": [task.id for task in due_soon_tasks],
    }


def create_task(owner_id: int, data: TaskInput) -> Task:
    """Validate and create a task in one transaction."""

    validate_task_input(data)
    task = Task(user_id=owner_id, **data.as_model_fields())
    _sync_completed_at(task)

    try:
        db.session.add(task)
        db.session.flush()
        if task.is_recurring and not task.recurrence_series_id:
            task.recurrence_series_id = task.id
        db.session.commit()
        return task
    except SQLAlchemyError as error:
        db.session.rollback()
        raise TaskPersistenceError from error


def update_task(task: Task, data: TaskInput) -> Task:
    """Validate and update an owned task in one transaction."""

    validate_task_input(data)
    previous_status = task.status

    for field_name, field_value in data.as_model_fields().items():
        setattr(task, field_name, field_value)

    _sync_completed_at(task, previous_status)
    if task.is_recurring and not task.recurrence_series_id:
        task.recurrence_series_id = task.id

    try:
        db.session.commit()
        return task
    except SQLAlchemyError as error:
        db.session.rollback()
        raise TaskPersistenceError from error


def toggle_task_completion(task: Task) -> TaskToggleResult:
    """Toggle completion and create the next recurrence when required."""

    project_id = task.project_id

    try:
        if task.status == "Completed":
            task.status = "Pending"
            task.completed_at = None
            message = f'Task "{task.title}" reopened.'
        else:
            task.status = "Completed"
            task.completed_at = datetime.utcnow()
            next_task = generate_next_occurrence(task)
            if next_task and next_task.deadline:
                message = (
                    f'Task "{task.title}" completed. '
                    f'Next occurrence created for {next_task.deadline.strftime("%d %b %Y")}.'
                )
            else:
                message = f'Task "{task.title}" completed.'

        db.session.commit()
        return TaskToggleResult(task=task, message=message, project_id=project_id)
    except (SQLAlchemyError, ValueError) as error:
        db.session.rollback()
        raise TaskPersistenceError from error


def delete_task(task: Task) -> DeletedTaskResult:
    """Delete a task while safely releasing any linked AI suggestion."""

    result = DeletedTaskResult(title=task.title, project_id=task.project_id)

    try:
        (
            AITaskSuggestion.query.filter_by(created_task_id=task.id).update(
                {
                    AITaskSuggestion.created_task_id: None,
                    AITaskSuggestion.status: "Pending",
                },
                synchronize_session=False,
            )
        )

        (
            DocumentTaskSuggestion.query.filter_by(created_task_id=task.id).update(
                {
                    DocumentTaskSuggestion.created_task_id: None,
                    DocumentTaskSuggestion.status: "Pending",
                },
                synchronize_session=False,
            )
        )

        (
            DocumentTaskSuggestion.query.filter_by(matched_task_id=task.id).update(
                {DocumentTaskSuggestion.matched_task_id: None},
                synchronize_session=False,
            )
        )

        db.session.delete(task)
        db.session.commit()
        return result
    except SQLAlchemyError as error:
        db.session.rollback()
        raise TaskPersistenceError from error

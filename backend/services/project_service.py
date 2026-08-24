"""Project business rules and persistence for LifeOS.

The Flask routes should handle HTTP concerns only. This module owns project
form normalisation, validation, ownership-safe queries, persistence, and the
factual project view models used by the Projects and Project Studio pages.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Mapping

from sqlalchemy import case
from sqlalchemy.exc import SQLAlchemyError

from database import db
from services.document_comparison_service import (
    delete_comparisons_referencing_documents,
)
from models import (
    Document,
    DocumentTaskSuggestion,
    Note,
    Project,
    ProjectQuestion,
    Task,
)


PROJECT_STATUSES = frozenset({"Planning", "In Progress", "Paused", "Completed"})
PROJECT_PRIORITIES = frozenset({"Low", "Medium", "High", "Critical"})

IMPORTANCE_ORDER = {
    "Low": 1,
    "Medium": 2,
    "High": 3,
    "Critical": 4,
}


class ProjectValidationError(ValueError):
    """Raised when submitted project data is not valid."""


class ProjectNotFoundError(LookupError):
    """Raised when a project does not exist for the requested owner."""


class ProjectPersistenceError(RuntimeError):
    """Raised when a database operation for a project cannot be completed."""


@dataclass(frozen=True)
class ProjectInput:
    """Normalised values received from a project form."""

    title: str
    project_type: str | None
    description: str | None
    goal: str | None
    tech_stack: str | None
    project_folder: str | None
    github_link: str | None
    demo_link: str | None
    start_date: date | None
    deadline: date | None
    status: str
    priority: str
    current_phase: str | None
    progress: int

    def as_model_fields(self) -> dict[str, Any]:
        """Return fields that can safely be assigned to a Project model."""

        return {
            "title": self.title,
            "project_type": self.project_type,
            "description": self.description,
            "goal": self.goal,
            "tech_stack": self.tech_stack,
            "project_folder": self.project_folder,
            "github_link": self.github_link,
            "demo_link": self.demo_link,
            "start_date": self.start_date,
            "deadline": self.deadline,
            "status": self.status,
            "priority": self.priority,
            "current_phase": self.current_phase,
            "progress": self.progress,
        }


def _parse_date(value: str | None) -> date | None:
    """Convert an HTML date value into a Python date object."""

    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _clean_optional_text(value: str | None) -> str | None:
    """Trim optional text and store empty values as ``None``."""

    if value is None:
        return None

    cleaned = value.strip()
    return cleaned or None


def _parse_progress(value: str | int | None) -> int:
    """Convert progress into an integer between zero and one hundred."""

    try:
        progress = int(value or 0)
    except (TypeError, ValueError):
        progress = 0

    return max(0, min(100, progress))


def build_project_input(form: Mapping[str, Any]) -> ProjectInput:
    """Create a stable project input object from submitted form values."""

    no_deadline = form.get("no_deadline") == "on"
    deadline = None if no_deadline else _parse_date(form.get("deadline"))

    status = (form.get("status") or "In Progress").strip()
    priority = (form.get("priority") or "Medium").strip()

    return ProjectInput(
        title=(form.get("title") or "").strip(),
        project_type=_clean_optional_text(form.get("project_type")),
        description=_clean_optional_text(form.get("description")),
        goal=_clean_optional_text(form.get("goal")),
        tech_stack=_clean_optional_text(form.get("tech_stack")),
        project_folder=_clean_optional_text(form.get("project_folder")),
        github_link=_clean_optional_text(form.get("github_link")),
        demo_link=_clean_optional_text(form.get("demo_link")),
        start_date=_parse_date(form.get("start_date")),
        deadline=deadline,
        status=status,
        priority=priority,
        current_phase=_clean_optional_text(form.get("current_phase")),
        progress=_parse_progress(form.get("progress")),
    )


def validate_project_input(data: ProjectInput) -> None:
    """Raise ``ProjectValidationError`` when submitted data is invalid."""

    if not data.title:
        raise ProjectValidationError("Project title is required.")

    if len(data.title) > 150:
        raise ProjectValidationError(
            "Project title must contain 150 characters or fewer."
        )

    if data.status not in PROJECT_STATUSES:
        raise ProjectValidationError("Please choose a valid project status.")

    if data.priority not in PROJECT_PRIORITIES:
        raise ProjectValidationError("Please choose a valid project priority.")

    if data.start_date and data.deadline and data.deadline < data.start_date:
        raise ProjectValidationError(
            "The project deadline cannot be before its start date."
        )


def get_owned_project(project_id: int, owner_id: int) -> Project | None:
    """Return a project only when it belongs to the requested user."""

    return Project.query.filter_by(id=project_id, user_id=owner_id).first()


def require_owned_project(project_id: int, owner_id: int) -> Project:
    """Return an owned project or raise a neutral not-found error."""

    project = get_owned_project(project_id, owner_id)
    if project is None:
        raise ProjectNotFoundError
    return project


def list_owned_projects(owner_id: int) -> list[Project]:
    """Return the user's projects in the current product display order."""

    return (
        Project.query.filter_by(user_id=owner_id)
        .order_by(Project.updated_at.desc(), Project.created_at.desc())
        .all()
    )


def create_project(owner_id: int, data: ProjectInput) -> Project:
    """Validate and create a project in one transaction."""

    validate_project_input(data)
    project = Project(user_id=owner_id, **data.as_model_fields())

    try:
        db.session.add(project)
        db.session.commit()
        return project
    except SQLAlchemyError as error:
        db.session.rollback()
        raise ProjectPersistenceError from error


def update_project(project: Project, data: ProjectInput) -> Project:
    """Validate and update an existing project in one transaction."""

    validate_project_input(data)

    for field_name, field_value in data.as_model_fields().items():
        setattr(project, field_name, field_value)

    try:
        db.session.commit()
        return project
    except SQLAlchemyError as error:
        db.session.rollback()
        raise ProjectPersistenceError from error


def delete_project(project: Project) -> str:
    """Delete a project and return its title for the confirmation message."""

    project_title = project.title
    document_ids = [
        document.id
        for document in project.documents
        if document.id is not None
    ]

    try:
        # Step 13A: document comparison foreign keys intentionally use
        # ON DELETE NO ACTION on SQL Server. Remove dependent comparisons
        # first, in the same transaction, before project.documents cascade.
        delete_comparisons_referencing_documents(
            document_ids
        )

        # Step 14: SQL Server version-family references use NO ACTION.
        # Detach the project's document rows before ORM cascades remove both
        # documents and their version-family metadata.
        for document in project.documents:
            document.version_family_id = None

        db.session.flush()

        db.session.delete(project)
        db.session.commit()
        return project_title

    except SQLAlchemyError as error:
        db.session.rollback()
        raise ProjectPersistenceError from error


def is_open_task(task: Task) -> bool:
    """Return whether a task still represents unfinished work."""

    return task.status != "Completed"


def calculate_task_progress(tasks: list[Task], fallback_progress: int = 0) -> int:
    """Use task completion when tasks exist; otherwise use saved progress."""

    if not tasks:
        return max(0, min(100, fallback_progress or 0))

    completed = sum(1 for task in tasks if task.status == "Completed")
    return round(completed / len(tasks) * 100)


def select_next_task(tasks: list[Task], today: date) -> Task | None:
    """Choose one factual next action without unsupported AI claims."""

    open_tasks = [task for task in tasks if is_open_task(task)]
    if not open_tasks:
        return None

    workable_tasks = [task for task in open_tasks if task.status != "Blocked"]
    candidates = workable_tasks or open_tasks

    def sort_key(task: Task) -> tuple[Any, ...]:
        is_overdue = bool(task.deadline and task.deadline < today)
        is_due_today = task.deadline == today
        is_in_progress = task.status == "In Progress"
        is_blocked = task.status == "Blocked"

        return (
            0 if is_overdue else 1,
            0 if is_due_today else 1,
            0 if is_in_progress else 1,
            1 if is_blocked else 0,
            task.deadline is None,
            task.deadline or date.max,
            -IMPORTANCE_ORDER.get(task.importance, 0),
            -(task.priority_score or 0),
            task.id,
        )

    return sorted(candidates, key=sort_key)[0]


def build_project_health(
    project: Project,
    tasks: list[Task],
    today: date,
) -> dict[str, str]:
    """Return a factual project-health label based on current data."""

    open_tasks = [task for task in tasks if is_open_task(task)]
    overdue_count = sum(
        1
        for task in open_tasks
        if task.deadline and task.deadline < today
    )
    blocked_count = sum(1 for task in open_tasks if task.status == "Blocked")
    due_soon_count = sum(
        1
        for task in open_tasks
        if task.deadline
        and today <= task.deadline <= today + timedelta(days=7)
    )

    if project.status == "Completed":
        return {
            "label": "Completed",
            "tone": "success",
            "message": "The project is marked complete.",
        }

    if project.status == "Paused":
        return {
            "label": "Paused",
            "tone": "neutral",
            "message": "Work is currently paused.",
        }

    if overdue_count:
        word = "task" if overdue_count == 1 else "tasks"
        return {
            "label": "Needs attention",
            "tone": "danger",
            "message": f"{overdue_count} overdue {word}.",
        }

    if blocked_count:
        word = "task" if blocked_count == 1 else "tasks"
        return {
            "label": "Blocked work",
            "tone": "warning",
            "message": f"{blocked_count} blocked {word} need review.",
        }

    if (
        project.deadline
        and today <= project.deadline <= today + timedelta(days=7)
        and open_tasks
    ):
        return {
            "label": "Deadline approaching",
            "tone": "warning",
            "message": "The project deadline is within seven days.",
        }

    if due_soon_count:
        word = "task" if due_soon_count == 1 else "tasks"
        return {
            "label": "Upcoming work",
            "tone": "info",
            "message": f"{due_soon_count} {word} due this week.",
        }

    if not tasks:
        return {
            "label": "Ready to plan",
            "tone": "neutral",
            "message": "No project tasks have been added yet.",
        }

    if not open_tasks:
        return {
            "label": "Tasks complete",
            "tone": "success",
            "message": "All connected tasks are completed.",
        }

    return {
        "label": "On track",
        "tone": "success",
        "message": "No overdue or blocked work detected.",
    }


def _owned_project_tasks(project_id: int, owner_id: int) -> list[Task]:
    """Return project tasks while enforcing task ownership as defence in depth."""

    return (
        Task.query.filter_by(project_id=project_id, user_id=owner_id)
        .order_by(Task.created_at.desc())
        .all()
    )


def build_project_card(
    project: Project,
    owner_id: int,
    today: date,
) -> dict[str, Any]:
    """Create the compact view model used by the Projects page."""

    tasks = _owned_project_tasks(project.id, owner_id)
    total_tasks = len(tasks)
    completed_tasks = sum(1 for task in tasks if task.status == "Completed")
    open_tasks = [task for task in tasks if is_open_task(task)]
    overdue_count = sum(
        1
        for task in open_tasks
        if task.deadline and task.deadline < today
    )
    blocked_count = sum(1 for task in open_tasks if task.status == "Blocked")
    note_count = Note.query.filter_by(
        project_id=project.id,
        user_id=owner_id,
    ).count()

    return {
        "project": project,
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "open_tasks": len(open_tasks),
        "overdue_count": overdue_count,
        "blocked_count": blocked_count,
        "note_count": note_count,
        "progress": calculate_task_progress(tasks, project.progress),
        "health": build_project_health(project, tasks, today),
        "next_task": select_next_task(tasks, today),
    }


def build_projects_overview(owner_id: int, today: date | None = None) -> dict[str, Any]:
    """Build the complete Projects-page view model for one user."""

    effective_today = today or date.today()
    projects = list_owned_projects(owner_id)
    project_cards = [
        build_project_card(project, owner_id, effective_today)
        for project in projects
    ]

    active_count = sum(
        1
        for card in project_cards
        if card["project"].status not in {"Completed", "Paused"}
    )
    attention_count = sum(
        1
        for card in project_cards
        if card["health"]["tone"] in {"danger", "warning"}
    )
    completed_count = sum(
        1
        for card in project_cards
        if card["project"].status == "Completed"
    )

    return {
        "projects": projects,
        "project_cards": project_cards,
        "active_count": active_count,
        "attention_count": attention_count,
        "completed_count": completed_count,
    }


def build_project_workspace(
    project_id: int,
    owner_id: int,
    today: date | None = None,
) -> dict[str, Any]:
    """Build the Project Studio view model for an owned project."""

    project = require_owned_project(project_id, owner_id)
    effective_today = today or date.today()
    upcoming_limit = effective_today + timedelta(days=7)
    tasks = _owned_project_tasks(project.id, owner_id)

    tasks.sort(
        key=lambda task: (
            task.status == "Completed",
            task.status == "Blocked",
            task.deadline is None,
            task.deadline or date.max,
            -IMPORTANCE_ORDER.get(task.importance, 0),
            -(task.priority_score or 0),
        )
    )

    total_tasks = len(tasks)
    completed_tasks = sum(1 for task in tasks if task.status == "Completed")
    pending_tasks = sum(1 for task in tasks if task.status == "Pending")
    in_progress_tasks = sum(1 for task in tasks if task.status == "In Progress")
    blocked_tasks = sum(1 for task in tasks if task.status == "Blocked")

    overdue_tasks = [
        task
        for task in tasks
        if task.deadline
        and task.deadline < effective_today
        and task.status != "Completed"
    ]
    due_soon_tasks = [
        task
        for task in tasks
        if task.deadline
        and effective_today <= task.deadline <= upcoming_limit
        and task.status != "Completed"
    ]
    high_priority_tasks = [
        task
        for task in tasks
        if task.importance in {"High", "Critical"}
        and task.status != "Completed"
    ]

    attention_tasks: list[Task] = []
    seen_task_ids: set[int] = set()
    candidates = (
        overdue_tasks
        + [task for task in tasks if task.status == "Blocked"]
        + due_soon_tasks
    )
    for task in candidates:
        if task.id not in seen_task_ids:
            attention_tasks.append(task)
            seen_task_ids.add(task.id)

    project_notes_query = Note.query.filter_by(
        project_id=project.id,
        user_id=owner_id,
    )
    notes_count = project_notes_query.count()
    recent_notes = (
        project_notes_query.order_by(Note.updated_at.desc()).limit(6).all()
    )

    document_suggestions = (
        DocumentTaskSuggestion.query
        .join(
            Document,
            DocumentTaskSuggestion.document_id == Document.id,
        )
        .filter(
            Document.project_id == project.id,
            DocumentTaskSuggestion.user_id == owner_id,
        )
        .order_by(
            case(
                (DocumentTaskSuggestion.status == "Pending", 0),
                (DocumentTaskSuggestion.status == "Approved", 1),
                (DocumentTaskSuggestion.status == "Linked", 2),
                else_=3,
            ),
            DocumentTaskSuggestion.created_at.desc(),
            DocumentTaskSuggestion.id.desc(),
        )
        .limit(80)
        .all()
    )

    pending_document_suggestions = [
        suggestion
        for suggestion in document_suggestions
        if suggestion.status == "Pending"
    ]

    project_documents = (
        Document.query
        .filter_by(project_id=project.id)
        .order_by(
            Document.uploaded_at.desc(),
            Document.id.desc(),
        )
        .all()
    )

    searchable_project_documents = [
        document
        for document in project_documents
        if str(document.extracted_text or "").strip()
    ]

    project_question_query = (
        ProjectQuestion.query
        .filter_by(
            project_id=project.id,
            user_id=owner_id,
        )
    )

    project_question_count = project_question_query.count()

    project_question_history = (
        project_question_query
        .order_by(
            ProjectQuestion.created_at.desc(),
            ProjectQuestion.id.desc(),
        )
        .limit(40)
        .all()
    )

    module_names = sorted({task.module for task in tasks if task.module})
    days_to_deadline = None
    if project.deadline:
        days_to_deadline = (project.deadline - effective_today).days

    return {
        "project": project,
        "tasks": tasks,
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "pending_tasks": pending_tasks,
        "in_progress_tasks": in_progress_tasks,
        "blocked_tasks": blocked_tasks,
        "overdue_tasks": overdue_tasks,
        "due_soon_tasks": due_soon_tasks,
        "high_priority_tasks": high_priority_tasks,
        "attention_tasks": attention_tasks[:6],
        "task_progress": calculate_task_progress(tasks, project.progress),
        "module_names": module_names,
        "next_task": select_next_task(tasks, effective_today),
        "project_health": build_project_health(project, tasks, effective_today),
        "days_to_deadline": days_to_deadline,
        "recent_notes": recent_notes,
        "notes_count": notes_count,
        "document_suggestions": document_suggestions,
        "pending_document_suggestions": pending_document_suggestions,
        "document_suggestion_count": len(document_suggestions),
        "pending_document_suggestion_count": len(pending_document_suggestions),
        "project_documents": project_documents,
        "project_document_count": len(project_documents),
        "searchable_project_document_count": len(searchable_project_documents),
        "project_question_history": project_question_history,
        "project_question_count": project_question_count,
        "today": effective_today,
    }

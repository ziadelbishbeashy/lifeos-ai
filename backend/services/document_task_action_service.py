"""Human-approved task conversion for Document Brain findings.

Step 9 keeps AI-detected work reviewable. Suggestions can be created directly,
edited first, created in bulk, ignored, or reviewed against a possible existing
project task. Source provenance stays on the suggestion record and is never
editable by the browser.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping

from sqlalchemy import case
from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import (
    Document,
    DocumentTaskSuggestion,
    Project,
    Task,
)
from services.task_duplicate_service import (
    TaskDuplicateAssessment,
    assess_task_duplicate,
)
from services.task_service import (
    TASK_IMPORTANCE_LEVELS,
    TASK_STATUSES,
    normalize_task_tags,
)


PRIORITY_SCORES = {
    "Low": 25,
    "Medium": 50,
    "High": 80,
    "Critical": 95,
}


class DocumentSuggestionNotFoundError(LookupError):
    """Raised when a suggestion is not owned by the user."""


class DocumentSuggestionWorkflowError(RuntimeError):
    """Raised when the requested suggestion action is invalid."""


class DocumentSuggestionDuplicateError(DocumentSuggestionWorkflowError):
    """Raised when creation would probably duplicate an existing task."""

    def __init__(
        self,
        task: Task,
        assessment: TaskDuplicateAssessment | None = None,
    ):
        self.task = task
        self.assessment = assessment
        super().__init__(
            "A similar project task already exists. Review the existing task "
            "before creating another one."
        )


class DocumentSuggestionPersistenceError(RuntimeError):
    """Raised when suggestion changes cannot be saved."""


@dataclass(frozen=True)
class DocumentSuggestionTaskInput:
    """Editable task fields approved by the user before task creation."""

    project_id: int
    title: str
    description: str | None
    priority: str
    deadline: date | None
    tags: str | None
    status: str


@dataclass(frozen=True)
class BulkSuggestionCreationResult:
    """Outcome of one user-approved bulk creation request."""

    created_tasks: tuple[Task, ...]
    duplicate_suggestions: tuple[DocumentTaskSuggestion, ...]
    skipped_suggestions: tuple[DocumentTaskSuggestion, ...]

    @property
    def created_count(self) -> int:
        return len(self.created_tasks)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicate_suggestions)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_suggestions)


def require_owned_document_suggestion(
    *,
    document_id: int,
    suggestion_id: int,
    user_id: int,
) -> DocumentTaskSuggestion:
    """Return a suggestion only when its document belongs to the user."""

    suggestion = (
        DocumentTaskSuggestion.query
        .join(
            Document,
            DocumentTaskSuggestion.document_id == Document.id,
        )
        .join(
            Project,
            Document.project_id == Project.id,
        )
        .filter(
            DocumentTaskSuggestion.id == suggestion_id,
            DocumentTaskSuggestion.document_id == document_id,
            DocumentTaskSuggestion.user_id == user_id,
            Project.user_id == user_id,
        )
        .first()
    )

    if suggestion is None:
        raise DocumentSuggestionNotFoundError(
            "The requested document suggestion was not found."
        )

    return suggestion


def list_document_suggestions(
    *,
    document_id: int,
    user_id: int,
) -> list[DocumentTaskSuggestion]:
    """Return suggestion history for one owned document across analyses."""

    owned_document = (
        Document.query
        .join(Project, Document.project_id == Project.id)
        .filter(
            Document.id == document_id,
            Project.user_id == user_id,
        )
        .first()
    )

    if owned_document is None:
        raise DocumentSuggestionNotFoundError(
            "The requested document was not found."
        )

    return (
        DocumentTaskSuggestion.query
        .filter_by(
            document_id=document_id,
            user_id=user_id,
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
        .all()
    )


def list_project_document_suggestions(
    *,
    project_id: int,
    user_id: int,
    limit: int = 80,
) -> list[DocumentTaskSuggestion]:
    """Return document-derived work connected to one owned project."""

    project = Project.query.filter_by(
        id=project_id,
        user_id=user_id,
    ).first()

    if project is None:
        raise DocumentSuggestionNotFoundError(
            "The requested project was not found."
        )

    return (
        DocumentTaskSuggestion.query
        .join(
            Document,
            DocumentTaskSuggestion.document_id == Document.id,
        )
        .filter(
            Document.project_id == project_id,
            DocumentTaskSuggestion.user_id == user_id,
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
        .limit(max(1, min(int(limit), 200)))
        .all()
    )


def default_suggestion_task_input(
    *,
    suggestion: DocumentTaskSuggestion,
) -> DocumentSuggestionTaskInput:
    """Build the default preview shown before user confirmation."""

    project_id = suggestion.document.project_id

    if not project_id:
        raise DocumentSuggestionWorkflowError(
            "This document is not connected to a project."
        )

    return DocumentSuggestionTaskInput(
        project_id=project_id,
        title=(suggestion.title or "").strip()[:200],
        description=(suggestion.description or "").strip() or None,
        priority=_normalise_priority(suggestion.priority),
        deadline=suggestion.deadline,
        tags=normalize_task_tags(suggestion.tags),
        status="Pending",
    )


def build_suggestion_task_input(
    *,
    form: Mapping[str, Any],
    suggestion: DocumentTaskSuggestion,
    user_id: int,
) -> DocumentSuggestionTaskInput:
    """Validate user edits without allowing source provenance to be edited."""

    raw_project_id = form.get("project_id")

    try:
        project_id = int(raw_project_id)
    except (TypeError, ValueError) as error:
        raise DocumentSuggestionWorkflowError(
            "Please choose a valid project."
        ) from error

    _require_owned_project(
        project_id=project_id,
        user_id=user_id,
    )

    title = " ".join(
        str(form.get("title") or "").strip().split()
    )

    if not title:
        raise DocumentSuggestionWorkflowError(
            "Task title is required."
        )

    if len(title) > 200:
        raise DocumentSuggestionWorkflowError(
            "Task title must contain 200 characters or fewer."
        )

    description = str(
        form.get("description") or ""
    ).strip() or None

    if description and len(description) > 5000:
        raise DocumentSuggestionWorkflowError(
            "Task description is too long."
        )

    priority = _normalise_priority(
        form.get("priority")
    )

    status = str(
        form.get("status") or "Pending"
    ).strip()

    if status not in TASK_STATUSES:
        raise DocumentSuggestionWorkflowError(
            "Please choose a valid task status."
        )

    deadline = _parse_date(
        form.get("deadline")
    )

    tags = normalize_task_tags(
        form.get("tags")
    )

    return DocumentSuggestionTaskInput(
        project_id=project_id,
        title=title,
        description=description,
        priority=priority,
        deadline=deadline,
        tags=tags,
        status=status,
    )


def preview_duplicate_assessment(
    *,
    suggestion: DocumentTaskSuggestion,
    user_id: int,
    task_input: DocumentSuggestionTaskInput | None = None,
) -> TaskDuplicateAssessment:
    """Return the live Step 11 duplicate decision for the proposed task."""

    data = task_input or default_suggestion_task_input(
        suggestion=suggestion
    )

    _require_owned_project(
        project_id=data.project_id,
        user_id=user_id,
    )

    existing_tasks = (
        Task.query
        .filter_by(
            user_id=user_id,
            project_id=data.project_id,
        )
        .all()
    )

    # A suggestion already accepted is not compared to the task it created.
    if suggestion.created_task_id:
        existing_tasks = [
            task
            for task in existing_tasks
            if task.id != suggestion.created_task_id
        ]

    return assess_task_duplicate(
        suggestion_title=data.title,
        suggestion_description=data.description,
        existing_tasks=existing_tasks,
    )


def preview_possible_duplicate(
    *,
    suggestion: DocumentTaskSuggestion,
    user_id: int,
    task_input: DocumentSuggestionTaskInput | None = None,
) -> Task | None:
    """Backward-compatible helper returning only the best duplicate task."""

    return preview_duplicate_assessment(
        suggestion=suggestion,
        user_id=user_id,
        task_input=task_input,
    ).matched_task

def approve_document_suggestion(
    *,
    suggestion: DocumentTaskSuggestion,
    user_id: int,
    allow_possible_duplicate: bool = False,
    task_input: DocumentSuggestionTaskInput | None = None,
) -> Task:
    """Create a task only after explicit user approval."""

    if (
        suggestion.status == "Approved"
        and suggestion.created_task_id
    ):
        existing_created_task = Task.query.filter_by(
            id=suggestion.created_task_id,
            user_id=user_id,
        ).first()

        if existing_created_task is not None:
            return existing_created_task

    if suggestion.status == "Linked" and suggestion.created_task_id:
        linked_task = Task.query.filter_by(
            id=suggestion.created_task_id,
            user_id=user_id,
        ).first()

        if linked_task is not None:
            return linked_task

    if suggestion.status == "Rejected":
        raise DocumentSuggestionWorkflowError(
            "This suggestion was ignored. Analyse the document again "
            "to generate a new suggestion."
        )

    _require_suggestion_owner(
        suggestion=suggestion,
        user_id=user_id,
    )

    data = task_input or default_suggestion_task_input(
        suggestion=suggestion
    )

    duplicate_assessment = preview_duplicate_assessment(
        suggestion=suggestion,
        user_id=user_id,
        task_input=data,
    )

    possible_duplicate = duplicate_assessment.matched_task

    if possible_duplicate is not None:
        suggestion.matched_task_id = possible_duplicate.id
        suggestion.match_score = duplicate_assessment.overall_score

        if not allow_possible_duplicate:
            try:
                db.session.commit()
            except SQLAlchemyError as error:
                db.session.rollback()
                raise DocumentSuggestionPersistenceError(
                    "LifeOS could not save the duplicate review."
                ) from error

            raise DocumentSuggestionDuplicateError(
                possible_duplicate,
                duplicate_assessment,
            )
    else:
        suggestion.matched_task_id = None
        suggestion.match_score = 0.0

    task = _prepare_task_from_suggestion(
        suggestion=suggestion,
        user_id=user_id,
        task_input=data,
    )

    try:
        db.session.add(task)
        db.session.flush()
        _mark_suggestion_created(
            suggestion=suggestion,
            task=task,
        )
        db.session.commit()
        return task

    except SQLAlchemyError as error:
        db.session.rollback()
        raise DocumentSuggestionPersistenceError(
            "LifeOS could not create the approved task."
        ) from error


def bulk_create_document_suggestions(
    *,
    suggestion_ids: list[int],
    user_id: int,
    document_id: int | None = None,
    project_id: int | None = None,
) -> BulkSuggestionCreationResult:
    """Create selected non-duplicate suggestions in one confirmation action."""

    cleaned_ids = []
    seen: set[int] = set()

    for raw_id in suggestion_ids:
        try:
            suggestion_id = int(raw_id)
        except (TypeError, ValueError):
            continue

        if suggestion_id <= 0 or suggestion_id in seen:
            continue

        seen.add(suggestion_id)
        cleaned_ids.append(suggestion_id)

    if not cleaned_ids:
        raise DocumentSuggestionWorkflowError(
            "Select at least one task suggestion."
        )

    query = (
        DocumentTaskSuggestion.query
        .join(
            Document,
            DocumentTaskSuggestion.document_id == Document.id,
        )
        .join(
            Project,
            Document.project_id == Project.id,
        )
        .filter(
            DocumentTaskSuggestion.id.in_(cleaned_ids),
            DocumentTaskSuggestion.user_id == user_id,
            Project.user_id == user_id,
        )
    )

    if document_id is not None:
        query = query.filter(
            DocumentTaskSuggestion.document_id == document_id
        )

    if project_id is not None:
        query = query.filter(
            Document.project_id == project_id
        )

    suggestions = query.all()
    suggestion_map = {
        suggestion.id: suggestion
        for suggestion in suggestions
    }

    if len(suggestion_map) != len(cleaned_ids):
        raise DocumentSuggestionNotFoundError(
            "One or more selected suggestions were not found."
        )

    created_tasks: list[Task] = []
    duplicates: list[DocumentTaskSuggestion] = []
    skipped: list[DocumentTaskSuggestion] = []

    try:
        for suggestion_id in cleaned_ids:
            suggestion = suggestion_map[suggestion_id]

            if suggestion.status != "Pending":
                skipped.append(suggestion)
                continue

            data = default_suggestion_task_input(
                suggestion=suggestion
            )

            duplicate_assessment = preview_duplicate_assessment(
                suggestion=suggestion,
                user_id=user_id,
                task_input=data,
            )

            possible_duplicate = duplicate_assessment.matched_task

            if possible_duplicate is not None:
                suggestion.matched_task_id = possible_duplicate.id
                suggestion.match_score = duplicate_assessment.overall_score
                duplicates.append(suggestion)
                continue

            suggestion.matched_task_id = None
            suggestion.match_score = 0.0

            task = _prepare_task_from_suggestion(
                suggestion=suggestion,
                user_id=user_id,
                task_input=data,
            )

            db.session.add(task)
            db.session.flush()
            _mark_suggestion_created(
                suggestion=suggestion,
                task=task,
            )
            created_tasks.append(task)

        db.session.commit()

    except SQLAlchemyError as error:
        db.session.rollback()
        raise DocumentSuggestionPersistenceError(
            "LifeOS could not create the selected tasks."
        ) from error

    return BulkSuggestionCreationResult(
        created_tasks=tuple(created_tasks),
        duplicate_suggestions=tuple(duplicates),
        skipped_suggestions=tuple(skipped),
    )


def link_suggestion_to_existing_task(
    *,
    suggestion: DocumentTaskSuggestion,
    user_id: int,
) -> Task:
    """Compatibility action for older Step 9 flows."""

    if suggestion.status == "Rejected":
        raise DocumentSuggestionWorkflowError(
            "An ignored suggestion cannot be linked."
        )

    if not suggestion.matched_task_id:
        raise DocumentSuggestionWorkflowError(
            "This suggestion does not have a matching task."
        )

    existing_task = Task.query.filter_by(
        id=suggestion.matched_task_id,
        user_id=user_id,
        project_id=suggestion.document.project_id,
    ).first()

    if existing_task is None:
        raise DocumentSuggestionWorkflowError(
            "The possible matching task no longer exists."
        )

    try:
        suggestion.status = "Linked"
        suggestion.created_task_id = existing_task.id
        suggestion.updated_at = datetime.utcnow()
        db.session.commit()
        return existing_task

    except SQLAlchemyError as error:
        db.session.rollback()
        raise DocumentSuggestionPersistenceError(
            "LifeOS could not link the suggestion."
        ) from error


def reject_document_suggestion(
    suggestion: DocumentTaskSuggestion,
) -> str:
    """Keep the suggestion in history but mark it ignored."""

    if suggestion.status in {
        "Approved",
        "Linked",
    }:
        raise DocumentSuggestionWorkflowError(
            "This suggestion has already been accepted."
        )

    if suggestion.status == "Rejected":
        return "already_rejected"

    try:
        suggestion.status = "Rejected"
        suggestion.updated_at = datetime.utcnow()
        db.session.commit()
        return "rejected"

    except SQLAlchemyError as error:
        db.session.rollback()
        raise DocumentSuggestionPersistenceError(
            "LifeOS could not ignore the suggestion."
        ) from error


def _prepare_task_from_suggestion(
    *,
    suggestion: DocumentTaskSuggestion,
    user_id: int,
    task_input: DocumentSuggestionTaskInput,
) -> Task:
    _require_owned_project(
        project_id=task_input.project_id,
        user_id=user_id,
    )

    source = suggestion.source
    source_parts: list[str] = []

    if source.get("page"):
        source_parts.append(
            f"Page {source['page']}"
        )

    if source.get("section"):
        source_parts.append(
            str(source["section"])
        )

    document = suggestion.document
    source_label = (
        f'Created from Document Brain analysis of "{document.filename}"'
    )

    if source_parts:
        source_label += f" ({' · '.join(source_parts)})"

    completed_at = (
        datetime.utcnow()
        if task_input.status == "Completed"
        else None
    )

    return Task(
        user_id=user_id,
        project_id=task_input.project_id,
        title=task_input.title[:200],
        description=task_input.description,
        module="Document Brain",
        tags=task_input.tags,
        importance=task_input.priority,
        difficulty="Medium",
        deadline=task_input.deadline,
        status=task_input.status,
        priority_score=PRIORITY_SCORES.get(
            task_input.priority,
            50,
        ),
        reason=f"{source_label}.",
        completed_at=completed_at,
    )


def _mark_suggestion_created(
    *,
    suggestion: DocumentTaskSuggestion,
    task: Task,
) -> None:
    suggestion.status = "Approved"
    suggestion.created_task_id = task.id
    suggestion.updated_at = datetime.utcnow()


def _require_suggestion_owner(
    *,
    suggestion: DocumentTaskSuggestion,
    user_id: int,
) -> None:
    document = (
        Document.query
        .join(Project, Document.project_id == Project.id)
        .filter(
            Document.id == suggestion.document_id,
            Project.user_id == user_id,
        )
        .first()
    )

    if document is None or suggestion.user_id != user_id:
        raise DocumentSuggestionNotFoundError(
            "The related document was not found."
        )


def _require_owned_project(
    *,
    project_id: int,
    user_id: int,
) -> Project:
    project = Project.query.filter_by(
        id=project_id,
        user_id=user_id,
    ).first()

    if project is None:
        raise DocumentSuggestionWorkflowError(
            "The selected project was not found."
        )

    return project


def _normalise_priority(value: Any) -> str:
    priority = str(value or "Medium").strip().title()

    if priority not in TASK_IMPORTANCE_LEVELS:
        return "Medium"

    return priority


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None

    if isinstance(value, date):
        return value

    try:
        return datetime.strptime(
            str(value).strip(),
            "%Y-%m-%d",
        ).date()
    except (TypeError, ValueError) as error:
        raise DocumentSuggestionWorkflowError(
            "Please choose a valid due date."
        ) from error

"""Approve, link or reject Document Brain task suggestions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import (
    Document,
    DocumentTaskSuggestion,
    Project,
    Task,
)


PRIORITY_SCORES = {
    "Low": 25,
    "Medium": 50,
    "High": 80,
}


class DocumentSuggestionNotFoundError(LookupError):
    """Raised when a suggestion is not owned by the user."""


class DocumentSuggestionWorkflowError(RuntimeError):
    """Raised when the requested suggestion action is invalid."""


class DocumentSuggestionPersistenceError(RuntimeError):
    """Raised when suggestion changes cannot be saved."""


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


def approve_document_suggestion(
    *,
    suggestion: DocumentTaskSuggestion,
    user_id: int,
    allow_possible_duplicate: bool = False,
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

    if suggestion.status == "Rejected":
        raise DocumentSuggestionWorkflowError(
            "This suggestion was rejected. Analyse the document "
            "again to generate a new suggestion."
        )

    if (
        suggestion.matched_task_id
        and not allow_possible_duplicate
    ):
        raise DocumentSuggestionWorkflowError(
            "A similar project task already exists. Review the "
            "possible match before creating another task."
        )

    document = (
        Document.query
        .join(
            Project,
            Document.project_id == Project.id,
        )
        .filter(
            Document.id == suggestion.document_id,
            Project.user_id == user_id,
        )
        .first()
    )

    if document is None:
        raise DocumentSuggestionNotFoundError(
            "The related document was not found."
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

    description_parts: list[str] = []

    if suggestion.description:
        description_parts.append(
            suggestion.description
        )

    if source.get("evidence"):
        description_parts.append(
            f'Document evidence: “{source["evidence"]}”'
        )

    description_parts.append(
        f'Created from Document Brain analysis of '
        f'"{document.filename}".'
    )

    task = Task(
        user_id=user_id,
        project_id=document.project_id,
        title=suggestion.title[:200],
        description="\n\n".join(
            description_parts
        ),
        module="Document Brain",
        importance=suggestion.priority,
        difficulty="Medium",
        deadline=suggestion.deadline,
        status="Pending",
        priority_score=PRIORITY_SCORES.get(
            suggestion.priority,
            50,
        ),
        reason=(
            "Approved from Document Brain"
            + (
                f" ({' · '.join(source_parts)})."
                if source_parts
                else "."
            )
        ),
    )

    try:
        db.session.add(task)
        db.session.flush()

        suggestion.status = "Approved"
        suggestion.created_task_id = task.id
        suggestion.updated_at = datetime.utcnow()

        db.session.commit()

        return task

    except SQLAlchemyError as error:
        db.session.rollback()

        raise DocumentSuggestionPersistenceError(
            "LifeOS could not create the approved task."
        ) from error


def link_suggestion_to_existing_task(
    *,
    suggestion: DocumentTaskSuggestion,
    user_id: int,
) -> Task:
    """Approve a suggestion by linking it to its matching task."""

    if suggestion.status == "Rejected":
        raise DocumentSuggestionWorkflowError(
            "A rejected suggestion cannot be linked."
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
    """Reject a pending document suggestion."""

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
            "LifeOS could not reject the suggestion."
        ) from error
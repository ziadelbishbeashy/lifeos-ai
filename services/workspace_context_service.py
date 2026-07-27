"""Shared workspace context for LifeOS intelligence features."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from models import Document, Note, Project, Task


MAX_PROJECT_CONTEXT_TASKS = 150
TASK_DESCRIPTION_PREVIEW = 280

MAX_RELATED_PROJECT_NOTES = 10
RELATED_NOTE_PREVIEW = 360

MAX_PROJECT_DOCUMENTS = 10
DOCUMENT_SUMMARY_PREVIEW = 500
DOCUMENT_TEXT_PREVIEW = 700


class WorkspaceContextNotFoundError(LookupError):
    """Raised when requested workspace information is unavailable."""


def iso_date(value: Any) -> str | None:
    """Convert a date or datetime into ISO-formatted text."""

    if value is None:
        return None

    return value.isoformat()


def compact_text(
    value: Any,
    limit: int = 1000,
) -> str:
    """Clean unnecessary whitespace and limit long text."""

    cleaned = " ".join(str(value or "").split())

    if len(cleaned) <= limit:
        return cleaned

    return cleaned[: limit - 1].rstrip() + "…"


def require_owned_project(
    owner_id: int,
    project_id: int,
) -> Project:
    """Return a project only when it belongs to the requested user."""

    project = Project.query.filter_by(
        id=project_id,
        user_id=owner_id,
    ).first()

    if project is None:
        raise WorkspaceContextNotFoundError(
            "The requested project was not found."
        )

    return project


def build_project_tasks_context(
    owner_id: int,
    project_id: int,
) -> dict[str, Any]:
    """Build an organised summary of tasks linked to a project."""

    all_tasks = Task.query.filter_by(
        user_id=owner_id,
        project_id=project_id,
    ).all()

    status_rank = {
        "Blocked": 0,
        "In Progress": 1,
        "Pending": 2,
        "Completed": 3,
    }

    def task_sort_key(task: Task) -> tuple[Any, ...]:
        return (
            status_rank.get(task.status or "", 2),
            task.deadline is None,
            task.deadline or datetime.max.date(),
            -(task.priority_score or 0),
            task.id,
        )

    selected_tasks = sorted(
        all_tasks,
        key=task_sort_key,
    )[:MAX_PROJECT_CONTEXT_TASKS]

    status_summary = Counter(
        (task.status or "Unknown").strip() or "Unknown"
        for task in all_tasks
    )

    tasks_context: list[dict[str, Any]] = []

    for task in selected_tasks:
        tasks_context.append(
            {
                "id": task.id,
                "title": task.title,
                "description": compact_text(
                    task.description,
                    TASK_DESCRIPTION_PREVIEW,
                ),
                "module": task.module or "",
                "status": task.status or "Pending",
                "priority": task.importance or "Medium",
                "difficulty": task.difficulty or "Medium",
                "deadline": iso_date(task.deadline),
                "completed_at": iso_date(task.completed_at),
                "priority_score": task.priority_score or 0,
            }
        )

    tasks_were_limited = len(all_tasks) > len(tasks_context)

    return {
        "task_status_summary": dict(status_summary),
        "tasks": tasks_context,
        "context_counts": {
            "total_project_tasks": len(all_tasks),
            "tasks_considered": len(tasks_context),
            "tasks_limited": tasks_were_limited,
            "context_limited": tasks_were_limited,
        },
    }


def build_related_notes_context(
    owner_id: int,
    project_id: int,
    exclude_note_id: int | None = None,
) -> list[dict[str, Any]]:
    """Build context from recent notes linked to the same project."""

    query = Note.query.filter_by(
        user_id=owner_id,
        project_id=project_id,
    )

    if exclude_note_id is not None:
        query = query.filter(
            Note.id != exclude_note_id
        )

    related_notes = (
        query
        .order_by(Note.updated_at.desc())
        .limit(MAX_RELATED_PROJECT_NOTES)
        .all()
    )

    notes_context: list[dict[str, Any]] = []

    for note in related_notes:
        latest_completed_analysis = next(
            (
                analysis
                for analysis in note.analyses
                if analysis.status == "Completed"
            ),
            None,
        )

        summary = note.content

        if latest_completed_analysis is not None:
            summary = (
                latest_completed_analysis.insights.get("overview")
                or latest_completed_analysis.summary
                or note.content
            )

        notes_context.append(
            {
                "id": note.id,
                "title": note.title,
                "note_type": note.note_type or "Quick Note",
                "summary": compact_text(
                    summary,
                    RELATED_NOTE_PREVIEW,
                ),
                "is_pinned": bool(note.is_pinned),
                "created_at": iso_date(note.created_at),
                "updated_at": iso_date(note.updated_at),
            }
        )

    return notes_context


def build_project_documents_context(
    project_id: int,
) -> list[dict[str, Any]]:
    """Build context from documents linked to a project."""

    documents = (
        Document.query
        .filter_by(project_id=project_id)
        .order_by(Document.uploaded_at.desc())
        .limit(MAX_PROJECT_DOCUMENTS)
        .all()
    )

    documents_context: list[dict[str, Any]] = []

    for document in documents:
        documents_context.append(
            {
                "id": document.id,
                "filename": document.filename,
                "summary": compact_text(
                    document.summary,
                    DOCUMENT_SUMMARY_PREVIEW,
                ),
                "text_preview": compact_text(
                    document.extracted_text,
                    DOCUMENT_TEXT_PREVIEW,
                ),
                "detected_modules": compact_text(
                    document.detected_modules,
                    300,
                ),
                "extracted_tasks": compact_text(
                    document.extracted_tasks,
                    400,
                ),
                "uploaded_at": iso_date(document.uploaded_at),
                "has_extracted_text": bool(
                    document.extracted_text
                ),
            }
        )

    return documents_context


def build_project_context(
    owner_id: int,
    project_id: int,
    exclude_note_id: int | None = None,
) -> dict[str, Any]:
    """Build shared project context for LifeOS intelligence features."""

    project = require_owned_project(
        owner_id=owner_id,
        project_id=project_id,
    )

    task_context = build_project_tasks_context(
        owner_id=owner_id,
        project_id=project.id,
    )

    related_notes_context = build_related_notes_context(
        owner_id=owner_id,
        project_id=project.id,
        exclude_note_id=exclude_note_id,
    )

    documents_context = build_project_documents_context(
        project_id=project.id,
    )

    return {
        "project": {
            "id": project.id,
            "title": project.title,
            "description": compact_text(project.description),
            "goal": compact_text(project.goal),
            "project_type": project.project_type or "",
            "tech_stack": project.tech_stack or "",
            "status": project.status or "",
            "priority": project.priority or "",
            "current_phase": project.current_phase or "",
            "progress": project.progress or 0,
            "start_date": iso_date(project.start_date),
            "deadline": iso_date(project.deadline),
            "created_at": iso_date(project.created_at),
            "updated_at": iso_date(project.updated_at),
        },
        "task_status_summary": task_context[
            "task_status_summary"
        ],
        "tasks": task_context["tasks"],
        "recent_related_notes": related_notes_context,
        "documents": documents_context,
        "context_counts": {
            **task_context["context_counts"],
            "related_notes_considered": len(
                related_notes_context
            ),
            "documents_considered": len(
                documents_context
            ),
        },
    }
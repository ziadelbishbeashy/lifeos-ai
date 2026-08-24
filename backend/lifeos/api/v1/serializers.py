"""JSON serializers for API v1.

Serializers deliberately expose product concepts only. Internal retrieval ranks,
chunk identifiers, embeddings, provider details, and other implementation
internals do not cross the React API boundary.
"""

from __future__ import annotations

from typing import Any


def _iso(value):
    return value.isoformat() if value is not None else None


def serialize_project(project) -> dict[str, Any]:
    return {
        "id": project.id,
        "title": project.title,
        "project_type": project.project_type,
        "description": project.description,
        "goal": project.goal,
        "tech_stack": project.tech_stack,
        "project_folder": project.project_folder,
        "github_link": project.github_link,
        "demo_link": project.demo_link,
        "start_date": _iso(project.start_date),
        "deadline": _iso(project.deadline),
        "status": project.status,
        "priority": project.priority,
        "current_phase": project.current_phase,
        "progress": int(project.progress or 0),
        "created_at": _iso(project.created_at),
        "updated_at": _iso(project.updated_at),
    }


def serialize_project_summary(project) -> dict[str, Any]:
    return {
        "id": project.id,
        "title": project.title,
        "status": project.status,
        "priority": project.priority,
        "progress": int(project.progress or 0),
        "deadline": _iso(project.deadline),
    }


def serialize_task(task) -> dict[str, Any]:
    project = getattr(task, "project", None)
    return {
        "id": task.id,
        "project_id": task.project_id,
        "project": (
            {"id": project.id, "title": project.title}
            if project is not None
            else None
        ),
        "title": task.title,
        "description": task.description,
        "module": task.module,
        "tags": task.tags,
        "importance": task.importance,
        "difficulty": task.difficulty,
        "deadline": _iso(task.deadline),
        "status": task.status,
        "priority_score": task.priority_score,
        "reason": task.reason,
        "reminder_enabled": bool(task.reminder_enabled),
        "reminder_type": task.reminder_type,
        "reminder_datetime": _iso(task.reminder_datetime),
        "is_recurring": bool(task.is_recurring),
        "recurrence_type": task.recurrence_type,
        "recurrence_interval": task.recurrence_interval,
        "recurrence_end_date": _iso(task.recurrence_end_date),
        "next_occurrence_date": _iso(task.next_occurrence_date),
        "created_at": _iso(task.created_at),
        "completed_at": _iso(task.completed_at),
    }


def serialize_note_summary(note) -> dict[str, Any]:
    return {
        "id": note.id,
        "project_id": note.project_id,
        "title": note.title,
        "content": note.content,
        "note_type": note.note_type,
        "is_pinned": bool(note.is_pinned),
        "updated_at": _iso(note.updated_at),
    }


def serialize_document_summary(document) -> dict[str, Any]:
    return {
        "id": document.id,
        "project_id": document.project_id,
        "filename": document.filename,
        "version_label": document.version_label,
        "version_number": document.version_number,
        "is_current_version": bool(document.is_current_version),
        "uploaded_at": _iso(document.uploaded_at),
        "has_text": bool(str(document.extracted_text or "").strip()),
        "summary": document.summary,
    }


def serialize_project_card(card: dict[str, Any]) -> dict[str, Any]:
    project = card["project"]
    return {
        # The native React Projects page preserves the complete legacy card
        # presentation, so expose the same product-level project fields while
        # keeping retrieval/provider internals out of the API boundary.
        **serialize_project(project),
        "task_progress": int(card.get("progress") or 0),
        "total_tasks": int(card.get("total_tasks") or 0),
        "completed_tasks": int(card.get("completed_tasks") or 0),
        "open_tasks": int(card.get("open_tasks") or 0),
        "overdue_tasks": int(card.get("overdue_count") or 0),
        "note_count": int(card.get("note_count") or 0),
        "health": card.get("health"),
        "next_task": (
            serialize_task(card["next_task"])
            if card.get("next_task") is not None
            else None
        ),
    }

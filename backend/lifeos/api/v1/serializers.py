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


def serialize_note(note) -> dict[str, Any]:
    project = getattr(note, "project", None)
    return {
        **serialize_note_summary(note),
        "created_at": _iso(note.created_at),
        "project": (
            {"id": project.id, "title": project.title}
            if project is not None
            else None
        ),
    }


def serialize_note_analysis(analysis) -> dict[str, Any] | None:
    if analysis is None:
        return None
    return {
        "id": analysis.id,
        "status": analysis.status,
        "summary": analysis.summary,
        "insights": analysis.insights,
        "error_message": analysis.error_message,
        "created_at": _iso(analysis.created_at),
    }


def serialize_note_question(question) -> dict[str, Any]:
    return {
        "id": question.id,
        "question": question.question,
        "answer": question.answer,
        "status": question.status,
        "error_message": question.error_message,
        "created_at": _iso(question.created_at),
    }


def serialize_note_suggestion(suggestion) -> dict[str, Any]:
    return {
        "id": suggestion.id,
        "title": suggestion.title,
        "description": suggestion.description,
        "priority": suggestion.priority,
        "deadline": _iso(suggestion.deadline),
        "status": suggestion.status,
        "created_task_id": suggestion.created_task_id,
        "created_at": _iso(suggestion.created_at),
    }


def serialize_focus_distraction(item) -> dict[str, Any]:
    return {
        "id": item.id,
        "content": item.content,
        "captured_at": _iso(item.captured_at),
        "converted_task_id": item.converted_task_id,
    }


def serialize_focus_session(session) -> dict[str, Any] | None:
    if session is None:
        return None
    task = getattr(session, "task", None)
    task_project = getattr(task, "project", None) if task is not None else None
    return {
        "id": session.id,
        "task_id": session.task_id,
        "task": (
            {
                "id": task.id,
                "title": task.title,
                "project": (
                    {"id": task_project.id, "title": task_project.title}
                    if task_project is not None
                    else None
                ),
            }
            if task is not None
            else None
        ),
        "title": session.title,
        "goal": session.goal,
        "planned_minutes": session.planned_minutes,
        "actual_minutes": session.actual_minutes,
        "elapsed_seconds": session.elapsed_seconds,
        "status": session.status,
        "distraction_count": session.distraction_count,
        "goal_result": session.goal_result,
        "focus_rating": session.focus_rating,
        "notes": session.notes,
        "started_at": _iso(session.started_at),
        "completed_at": _iso(session.completed_at),
        "created_at": _iso(session.created_at),
        "distractions": [
            serialize_focus_distraction(item)
            for item in getattr(session, "distractions", [])
        ],
    }


def serialize_notification_preferences(preferences) -> dict[str, Any]:
    fields = (
        "email_enabled",
        "task_reminders_enabled",
        "custom_task_reminders_enabled",
        "overdue_alerts_enabled",
        "project_deadline_alerts_enabled",
        "project_risk_alerts_enabled",
        "daily_checkup_enabled",
        "weekly_summary_enabled",
        "monthly_analytics_enabled",
        "task_reminder_days_before",
        "project_reminder_days_before",
        "daily_checkup_time",
        "weekly_summary_day",
        "weekly_summary_time",
        "monthly_report_day",
        "monthly_report_time",
        "quiet_hours_start",
        "quiet_hours_end",
    )
    payload: dict[str, Any] = {}
    for field in fields:
        value = getattr(preferences, field, None)
        payload[field] = _iso(value) if value is not None and hasattr(value, "isoformat") else value
    return payload


def serialize_notification_log(log) -> dict[str, Any]:
    return {
        "id": log.id,
        "notification_type": log.notification_type,
        "sent_to": log.sent_to,
        "subject": log.subject,
        "status": log.status,
        "error_message": log.error_message,
        "task_id": log.task_id,
        "project_id": log.project_id,
        "sent_at": _iso(log.sent_at),
    }


def serialize_document(document) -> dict[str, Any]:
    project = getattr(document, "project", None)
    return {
        **serialize_document_summary(document),
        "project": (
            {"id": project.id, "title": project.title}
            if project is not None
            else None
        ),
        "is_versioned": bool(document.is_versioned),
        "is_historical_version": bool(document.is_historical_version),
        "version_change": document.version_change,
        "superseded_at": _iso(document.superseded_at),
        "text_character_count": len(str(document.extracted_text or "")),
    }


def serialize_document_analysis(analysis) -> dict[str, Any] | None:
    if analysis is None:
        return None
    return {
        "id": analysis.id,
        "status": analysis.status,
        "document_type": analysis.document_type,
        "summary": analysis.summary,
        "insights": analysis.insights,
        "error_message": analysis.error_message,
        "created_at": _iso(analysis.created_at),
    }


def serialize_document_question(question) -> dict[str, Any]:
    return {
        "id": question.id,
        "question": question.question,
        "answer": question.answer,
        "sources": question.sources,
        "status": question.status,
        "error_message": question.error_message,
        "created_at": _iso(question.created_at),
    }


def serialize_project_question(question) -> dict[str, Any]:
    return {
        "id": question.id,
        "project_id": question.project_id,
        "question": question.question,
        "answer": question.answer,
        "sources": question.sources,
        "status": question.status,
        "error_message": question.error_message,
        "created_at": _iso(question.created_at),
    }


def serialize_document_suggestion(suggestion) -> dict[str, Any]:
    return {
        "id": suggestion.id,
        "analysis_id": suggestion.analysis_id,
        "document_id": suggestion.document_id,
        "title": suggestion.title,
        "description": suggestion.description,
        "tags": suggestion.tags_list,
        "priority": suggestion.priority,
        "deadline": _iso(suggestion.deadline),
        "source": suggestion.source,
        "status": suggestion.status,
        "lifecycle_label": suggestion.lifecycle_label,
        "matched_task_id": suggestion.matched_task_id,
        "match_score": suggestion.match_score,
        "created_task_id": suggestion.created_task_id,
        "created_at": _iso(suggestion.created_at),
    }


def serialize_document_comparison(comparison) -> dict[str, Any]:
    document_a = getattr(comparison, "document_a", None)
    document_b = getattr(comparison, "document_b", None)
    return {
        "id": comparison.id,
        "document_a": serialize_document_summary(document_a) if document_a is not None else None,
        "document_b": serialize_document_summary(document_b) if document_b is not None else None,
        "summary": comparison.summary,
        "findings": comparison.findings,
        "status": comparison.status,
        "error_message": comparison.error_message,
        "created_at": _iso(comparison.created_at),
    }


def serialize_version_history(history) -> dict[str, Any] | None:
    if history is None:
        return None
    return {
        "current_document": serialize_document(history.current_document),
        "versions": [serialize_document(item) for item in history.versions],
        "family": (
            {
                "id": history.family.id,
                "name": history.family.name,
                "created_at": _iso(history.family.created_at),
            }
            if history.family is not None
            else None
        ),
    }


def json_safe(value):
    """Convert service-layer view models to JSON-safe product data."""
    from dataclasses import asdict, is_dataclass
    from datetime import date, datetime, time

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if is_dataclass(value):
        return json_safe(asdict(value))
    # Do not leak arbitrary ORM/provider internals. Unknown objects become text.
    return str(value)

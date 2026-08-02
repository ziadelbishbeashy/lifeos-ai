"""Notes domain service for LifeOS.

Routes should deal only with HTTP input/output. This module owns note validation,
ownership-safe queries, persistence, project-aware context construction, AI-result
persistence, and the suggested-task approval workflow.
"""

from __future__ import annotations

import hashlib
import json
from services.workspace_context_service import (
    WorkspaceContextNotFoundError,
    build_project_context as build_shared_project_context,
)
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import (
    AITaskSuggestion,
    Note,
    NoteAIAnalysis,
    NoteAIQuestion,
    Project,
    Task,
)


NOTE_TYPES = (
    "Quick Note",
    "Project Note",
    "Meeting Note",
    "Lecture Note",
    "Research Note",
    "Idea",
    "Daily Reflection",
)

PRIORITY_SCORES = {
    "Low": 25,
    "Medium": 50,
    "High": 80,
}




class NoteValidationError(ValueError):
    """Raised when submitted note input is invalid."""


class NoteNotFoundError(LookupError):
    """Raised when a note does not exist for the requested owner."""


class NoteSuggestionNotFoundError(LookupError):
    """Raised when an AI suggestion is not owned by the requested user."""


class NotePersistenceError(RuntimeError):
    """Raised when note data cannot be saved safely."""


class NoteWorkflowError(RuntimeError):
    """Raised when an AI-note action is invalid for the current state."""


@dataclass(frozen=True)
class NoteInput:
    title: str
    content: str
    note_type: str
    project_id: int | None
    is_pinned: bool

    def as_model_fields(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "note_type": self.note_type,
            "project_id": self.project_id,
            "is_pinned": self.is_pinned,
        }


@dataclass(frozen=True)
class NoteListResult:
    notes: list[Note]
    pinned_notes: list[Note]
    regular_notes: list[Note]
    projects: list[Project]
    search_text: str
    selected_type: str
    selected_project: str


@dataclass(frozen=True)
class NoteDetailsResult:
    note: Note
    latest_analysis: NoteAIAnalysis | None
    latest_failed_analysis: NoteAIAnalysis | None
    task_suggestions: list[AITaskSuggestion]
    question_history: list[NoteAIQuestion]
    insights: dict[str, Any]
    project_context: dict[str, Any] | None
    project_task_lookup: dict[int, Task]
    analysis_is_stale: bool


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def list_owned_projects(owner_id: int) -> list[Project]:
    return (
        Project.query.filter_by(user_id=owner_id)
        .order_by(Project.title.asc())
        .all()
    )


def resolve_project_id(raw_project_id: Any, owner_id: int) -> int | None:
    if raw_project_id in (None, ""):
        return None

    try:
        project_id = int(raw_project_id)
    except (TypeError, ValueError) as error:
        raise NoteValidationError("The selected project is invalid.") from error

    project = Project.query.filter_by(id=project_id, user_id=owner_id).first()
    if project is None:
        raise NoteValidationError(
            "The selected project does not belong to your workspace."
        )
    return project.id


def build_note_input(form: Mapping[str, Any], owner_id: int) -> NoteInput:
    return NoteInput(
        title=_clean_text(form.get("title")),
        content=_clean_text(form.get("content")),
        note_type=_clean_text(form.get("note_type")) or "Quick Note",
        project_id=resolve_project_id(form.get("project_id"), owner_id),
        is_pinned=form.get("is_pinned") == "on",
    )


def validate_note_input(data: NoteInput) -> None:
    if not data.title:
        raise NoteValidationError("Note title is required.")
    if len(data.title) > 255:
        raise NoteValidationError("Note title cannot exceed 255 characters.")
    if not data.content:
        raise NoteValidationError("Note content is required.")
    if len(data.content) > 20_000:
        raise NoteValidationError(
            "Note content cannot exceed 20,000 characters in this phase."
        )
    if data.note_type not in NOTE_TYPES:
        raise NoteValidationError("The selected note type is invalid.")


def get_owned_note(note_id: int, owner_id: int) -> Note | None:
    return Note.query.filter_by(id=note_id, user_id=owner_id).first()


def require_owned_note(note_id: int, owner_id: int) -> Note:
    note = get_owned_note(note_id, owner_id)
    if note is None:
        raise NoteNotFoundError
    return note


def require_owned_suggestion(
    note_id: int,
    suggestion_id: int,
    owner_id: int,
) -> AITaskSuggestion:
    suggestion = (
        AITaskSuggestion.query
        .join(Note, AITaskSuggestion.note_id == Note.id)
        .filter(
            AITaskSuggestion.id == suggestion_id,
            AITaskSuggestion.note_id == note_id,
            Note.user_id == owner_id,
        )
        .first()
    )
    if suggestion is None:
        raise NoteSuggestionNotFoundError
    return suggestion


def list_notes(
    owner_id: int,
    search_text: str = "",
    selected_type: str = "all",
    selected_project: str = "all",
) -> NoteListResult:
    search_text = _clean_text(search_text)
    selected_type = _clean_text(selected_type) or "all"
    selected_project = _clean_text(selected_project) or "all"

    query = Note.query.filter(Note.user_id == owner_id)

    if search_text:
        pattern = f"%{search_text}%"
        query = query.filter(
            or_(Note.title.ilike(pattern), Note.content.ilike(pattern))
        )

    if selected_type in NOTE_TYPES:
        query = query.filter(Note.note_type == selected_type)

    if selected_project == "general":
        query = query.filter(Note.project_id.is_(None))
    elif selected_project not in ("", "all"):
        try:
            project_id = int(selected_project)
        except ValueError:
            project_id = None
        if project_id is not None:
            owned_project = Project.query.filter_by(
                id=project_id,
                user_id=owner_id,
            ).first()
            if owned_project is not None:
                query = query.filter(Note.project_id == project_id)
            else:
                query = query.filter(Note.id == -1)

    notes = query.order_by(Note.is_pinned.desc(), Note.updated_at.desc()).all()
    return NoteListResult(
        notes=notes,
        pinned_notes=[note for note in notes if note.is_pinned],
        regular_notes=[note for note in notes if not note.is_pinned],
        projects=list_owned_projects(owner_id),
        search_text=search_text,
        selected_type=selected_type,
        selected_project=selected_project,
    )


def create_note(owner_id: int, data: NoteInput) -> Note:
    validate_note_input(data)
    note = Note(user_id=owner_id, **data.as_model_fields())
    try:
        db.session.add(note)
        db.session.commit()
        return note
    except SQLAlchemyError as error:
        db.session.rollback()
        raise NotePersistenceError from error


def update_note(note: Note, data: NoteInput) -> Note:
    validate_note_input(data)
    for name, value in data.as_model_fields().items():
        setattr(note, name, value)
    note.updated_at = datetime.utcnow()
    try:
        db.session.commit()
        return note
    except SQLAlchemyError as error:
        db.session.rollback()
        raise NotePersistenceError from error


def toggle_note_pin(note: Note) -> bool:
    note.is_pinned = not note.is_pinned
    note.updated_at = datetime.utcnow()
    try:
        db.session.commit()
        return note.is_pinned
    except SQLAlchemyError as error:
        db.session.rollback()
        raise NotePersistenceError from error


def delete_note(note: Note) -> str:
    title = note.title
    try:
        # Explicit deletes keep compatibility with existing databases that may
        # not yet enforce every cascade at the database level.
        NoteAIQuestion.query.filter_by(note_id=note.id).delete(
            synchronize_session=False
        )
        AITaskSuggestion.query.filter_by(note_id=note.id).delete(
            synchronize_session=False
        )
        NoteAIAnalysis.query.filter_by(note_id=note.id).delete(
            synchronize_session=False
        )
        db.session.delete(note)
        db.session.commit()
        return title
    except SQLAlchemyError as error:
        db.session.rollback()
        raise NotePersistenceError from error

def build_project_context(
    note: Note,
    owner_id: int,
) -> dict[str, Any] | None:
    """Build shared project context for an AI note."""

    if note.project_id is None:
        return None

    try:
        return build_shared_project_context(
            owner_id=owner_id,
            project_id=note.project_id,
            exclude_note_id=note.id,
        )
    except WorkspaceContextNotFoundError:
        return None


def build_note_fingerprint(
    note: Note,
    project_context: dict[str, Any] | None = None,
) -> str:
    source = {
        "note": {
            "title": note.title or "",
            "note_type": note.note_type or "",
            "content": note.content or "",
            "project_id": note.project_id,
        },
        "project_context": project_context,
    }
    serialized = json.dumps(
        source,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def get_latest_completed_analysis(
    note: Note,
    owner_id: int,
) -> NoteAIAnalysis | None:
    return (
        NoteAIAnalysis.query.filter_by(
            note_id=note.id,
            user_id=owner_id,
            status="Completed",
        )
        .order_by(NoteAIAnalysis.created_at.desc())
        .first()
    )


def analysis_is_stale(
    note: Note,
    analysis: NoteAIAnalysis | None,
    project_context: dict[str, Any] | None = None,
) -> bool:
    if not analysis:
        return False
    stored_fingerprint = analysis.insights.get("_source_fingerprint")
    if stored_fingerprint:
        return stored_fingerprint != build_note_fingerprint(note, project_context)
    return bool(
        note.updated_at
        and analysis.created_at
        and analysis.created_at < note.updated_at
    )


def get_project_task_lookup(
    note: Note,
    insights: dict[str, Any],
    owner_id: int,
) -> dict[int, Task]:
    if not note.project_id:
        return {}

    task_ids: set[int] = set()
    for match in insights.get("existing_task_matches", []):
        task_id = match.get("matched_task_id")
        if isinstance(task_id, int):
            task_ids.add(task_id)
    for action in insights.get("task_actions", []):
        task_id = action.get("matched_task_id")
        if isinstance(task_id, int):
            task_ids.add(task_id)

    if not task_ids:
        return {}

    tasks = Task.query.filter(
        Task.id.in_(task_ids),
        Task.user_id == owner_id,
        Task.project_id == note.project_id,
    ).all()
    return {task.id: task for task in tasks}


def build_note_details(note: Note, owner_id: int) -> NoteDetailsResult:
    project_context = build_project_context(note, owner_id)
    latest_analysis = get_latest_completed_analysis(note, owner_id)
    latest_failed_analysis = (
        NoteAIAnalysis.query.filter_by(
            note_id=note.id,
            user_id=owner_id,
            status="Failed",
        )
        .order_by(NoteAIAnalysis.created_at.desc())
        .first()
    )
    task_suggestions: list[AITaskSuggestion] = []
    if latest_analysis:
        task_suggestions = (
            AITaskSuggestion.query.filter_by(
                analysis_id=latest_analysis.id,
                note_id=note.id,
            )
            .order_by(AITaskSuggestion.created_at.asc())
            .all()
        )
    question_history = (
        NoteAIQuestion.query.filter_by(note_id=note.id, user_id=owner_id)
        .order_by(NoteAIQuestion.created_at.desc())
        .limit(20)
        .all()
    )
    insights = latest_analysis.insights if latest_analysis else {}
    return NoteDetailsResult(
        note=note,
        latest_analysis=latest_analysis,
        latest_failed_analysis=latest_failed_analysis,
        task_suggestions=task_suggestions,
        question_history=question_history,
        insights=insights,
        project_context=project_context,
        project_task_lookup=get_project_task_lookup(note, insights, owner_id),
        analysis_is_stale=analysis_is_stale(
            note,
            latest_analysis,
            project_context,
        ),
    )


def _build_suggestion_description(
    suggestion_data: dict[str, Any],
    note: Note,
) -> str:
    parts: list[str] = []
    description = _clean_text(suggestion_data.get("description"))
    reason = _clean_text(suggestion_data.get("reason"))
    evidence = _clean_text(suggestion_data.get("evidence"))
    if description:
        parts.append(description)
    if reason and reason.lower() not in description.lower():
        parts.append(f"Why it matters: {reason}")
    if evidence:
        parts.append(f'Note evidence: “{evidence}”')
    parts.append(f'Created from LifeOS note: "{note.title}".')
    return "\n\n".join(parts)


def save_completed_analysis(
    note: Note,
    owner_id: int,
    result: dict[str, Any],
    project_context: dict[str, Any] | None,
) -> NoteAIAnalysis:
    analysis_data = result["analysis"]
    insights_payload = dict(analysis_data.get("insights", {}))
    insights_payload["_source_fingerprint"] = build_note_fingerprint(
        note,
        project_context,
    )

    analysis = NoteAIAnalysis(
        note_id=note.id,
        user_id=owner_id,
        provider=result["provider"],
        model=result["model"],
        status="Completed",
        summary=analysis_data.get("summary"),
        tags_json=json.dumps(analysis_data.get("tags", []), ensure_ascii=False),
        deadlines_json=json.dumps(
            analysis_data.get("deadlines", []),
            ensure_ascii=False,
        ),
        decisions_json=json.dumps(
            analysis_data.get("decisions", []),
            ensure_ascii=False,
        ),
        questions_json=json.dumps(
            analysis_data.get("questions", []),
            ensure_ascii=False,
        ),
        insights_json=json.dumps(insights_payload, ensure_ascii=False),
    )

    try:
        db.session.add(analysis)
        db.session.flush()
        for suggestion_data in analysis_data.get("task_suggestions", []):
            deadline_value = None
            deadline_text = suggestion_data.get("deadline")
            if deadline_text:
                try:
                    deadline_value = datetime.strptime(
                        deadline_text,
                        "%Y-%m-%d",
                    ).date()
                except (TypeError, ValueError):
                    deadline_value = None

            db.session.add(
                AITaskSuggestion(
                    analysis_id=analysis.id,
                    note_id=note.id,
                    title=(suggestion_data.get("title") or "Untitled Task")[:255],
                    description=_build_suggestion_description(
                        suggestion_data,
                        note,
                    ),
                    priority=suggestion_data.get("priority", "Medium"),
                    deadline=deadline_value,
                    status="Pending",
                )
            )
        db.session.commit()
        return analysis
    except (SQLAlchemyError, KeyError, TypeError) as error:
        db.session.rollback()
        raise NotePersistenceError from error


def save_failed_analysis(note: Note, owner_id: int, message: str) -> None:
    try:
        db.session.add(
            NoteAIAnalysis(
                note_id=note.id,
                user_id=owner_id,
                provider="unknown",
                model="unknown",
                status="Failed",
                error_message=message,
            )
        )
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise NotePersistenceError from error


def save_completed_question(
    note: Note,
    analysis: NoteAIAnalysis,
    owner_id: int,
    question: str,
    result: dict[str, Any],
) -> NoteAIQuestion:
    record = NoteAIQuestion(
        note_id=note.id,
        analysis_id=analysis.id,
        user_id=owner_id,
        question=question,
        answer=result["answer"],
        provider=result["provider"],
        model=result["model"],
        status="Completed",
    )
    try:
        db.session.add(record)
        db.session.commit()
        return record
    except (SQLAlchemyError, KeyError) as error:
        db.session.rollback()
        raise NotePersistenceError from error


def save_failed_question(
    note: Note,
    analysis: NoteAIAnalysis,
    owner_id: int,
    question: str,
    message: str,
) -> None:
    try:
        db.session.add(
            NoteAIQuestion(
                note_id=note.id,
                analysis_id=analysis.id,
                user_id=owner_id,
                question=question,
                answer=None,
                provider="unknown",
                model="unknown",
                status="Failed",
                error_message=message,
            )
        )
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise NotePersistenceError from error


def approve_suggestion(
    note: Note,
    suggestion: AITaskSuggestion,
    owner_id: int,
) -> Task:
    if suggestion.status == "Approved" and suggestion.created_task_id:
        existing = Task.query.filter_by(
            id=suggestion.created_task_id,
            user_id=owner_id,
        ).first()
        if existing:
            return existing
    if suggestion.status == "Rejected":
        raise NoteWorkflowError(
            "This suggestion was rejected. Analyze the note again to create new suggestions."
        )

    task = Task(
        user_id=owner_id,
        project_id=note.project_id,
        title=suggestion.title[:200],
        description=suggestion.description,
        module="AI Notes",
        importance=suggestion.priority,
        difficulty="Medium",
        deadline=suggestion.deadline,
        status="Pending",
        priority_score=PRIORITY_SCORES.get(suggestion.priority, 50),
        reason=f'Approved from AI analysis of note "{note.title}".',
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
        raise NotePersistenceError from error


def reject_suggestion(suggestion: AITaskSuggestion) -> str:
    if suggestion.status == "Approved":
        raise NoteWorkflowError(
            "This suggestion already created a task and cannot be rejected here."
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
        raise NotePersistenceError from error

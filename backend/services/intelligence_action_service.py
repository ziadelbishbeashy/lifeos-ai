"""I9 — confirmation-gated actions for Ask LifeOS.

The intelligence layer may *propose* a small reviewed set of actions.  A model,
document, agent priority, or API request never performs a write directly.  A
proposal is persisted first, then an authenticated owner must confirm it; the
actual write is executed by existing deterministic LifeOS services.
"""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import Document, LifeOSActionProposal, Project
from services.document_ai_workflow_service import (
    DocumentAnalysisWorkflowError,
    analyse_owned_document,
)
from services.lifeos_activity_service import add_activity_event
from services.context_connection_service import persist_confirmed_action_connections
from services.note_service import NoteInput, NotePersistenceError, create_note
from services.task_service import TaskInput, TaskPersistenceError, create_task


ACTION_CREATE_TASK = "create_task"
ACTION_CREATE_NOTE = "create_note"
ACTION_REFRESH_DOCUMENT_ANALYSIS = "refresh_document_analysis"
ALLOWED_ACTION_TYPES = frozenset({
    ACTION_CREATE_TASK,
    ACTION_CREATE_NOTE,
    ACTION_REFRESH_DOCUMENT_ANALYSIS,
})
ALLOWED_PROPOSAL_STATUSES = frozenset({"pending", "executing", "confirmed", "dismissed", "failed"})


class IntelligenceActionError(RuntimeError):
    pass


class IntelligenceActionValidationError(IntelligenceActionError, ValueError):
    pass


class IntelligenceActionNotFoundError(IntelligenceActionError, LookupError):
    pass


class IntelligenceActionExecutionError(IntelligenceActionError):
    pass


def _clean(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _owned_project(project_id: int, owner_id: int) -> Project:
    project = Project.query.filter_by(id=int(project_id), user_id=int(owner_id)).first()
    if project is None:
        raise IntelligenceActionValidationError("The target project was not found in your workspace.")
    return project


def _owned_document(document_id: int, owner_id: int) -> Document:
    document = Document.query.filter_by(id=int(document_id), user_id=int(owner_id)).first()
    if document is None:
        raise IntelligenceActionValidationError("The target document was not found in your workspace.")
    if getattr(document, "is_historical_version", False):
        raise IntelligenceActionValidationError("Open the current document version before refreshing its analysis.")
    return document


def _sanitize_evidence(value: Any, *, owner_id: int, project_id: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for raw in value[:8]:
        if not isinstance(raw, dict):
            continue
        source_type = _clean(raw.get("source_type"), 64)
        source_id = raw.get("source_id")
        try:
            source_id = int(source_id) if source_id is not None else None
        except (TypeError, ValueError):
            source_id = None

        # Evidence is explanatory, not authorization.  Drop references that do
        # not belong to the authenticated scope rather than trusting them.
        if source_type == "document" and source_id is not None:
            document = Document.query.filter_by(id=source_id, user_id=owner_id).first()
            if document is None or (document.project_id is not None and int(document.project_id) != int(project_id)):
                continue
        if source_type == "project" and source_id is not None and int(source_id) != int(project_id):
            continue

        result.append({
            "source_type": source_type or "workspace",
            "source_id": source_id,
            "label": _clean(raw.get("label"), 255),
            "field": _clean(raw.get("field"), 120),
            "freshness": _clean(raw.get("freshness"), 40) or "current",
        })
    return result


def priority_action_options(priority: dict[str, Any]) -> list[dict[str, str]]:
    """Return reviewed actions the UI may offer for one I8 priority."""

    category = str(priority.get("category") or "")
    if category == "stale_document":
        return [
            {"type": ACTION_REFRESH_DOCUMENT_ANALYSIS, "label": "Refresh analysis", "risk_level": "medium"},
            {"type": ACTION_CREATE_TASK, "label": "Create task", "risk_level": "medium"},
            {"type": ACTION_CREATE_NOTE, "label": "Save note", "risk_level": "low"},
        ]
    if category in {"document_risk", "document_action", "missing_information", "project_deadline", "no_tasks", "missing_next_action"}:
        return [
            {"type": ACTION_CREATE_TASK, "label": "Create task", "risk_level": "medium"},
            {"type": ACTION_CREATE_NOTE, "label": "Save note", "risk_level": "low"},
        ]
    # Existing task priorities already point to a real Task.  Avoid creating a
    # duplicate task; a note is the only I9 write offered for these cases.
    if category in {"blocked_task", "overdue_task", "due_soon_task", "next_task"}:
        return [{"type": ACTION_CREATE_NOTE, "label": "Save note", "risk_level": "low"}]
    return [{"type": ACTION_CREATE_NOTE, "label": "Save note", "risk_level": "low"}]


def _proposal_payload_from_priority(
    *,
    action_type: str,
    project: Project,
    priority: dict[str, Any],
    owner_id: int,
) -> tuple[str, str, str, int | None, dict[str, Any], list[dict[str, Any]], str]:
    title = _clean(priority.get("title"), 220) or "LifeOS suggested action"
    reason = _clean(priority.get("reason"), 1600)
    recommended = _clean(priority.get("recommended_action"), 1200)
    severity = _clean(priority.get("severity"), 24).casefold() or "medium"
    evidence = _sanitize_evidence(priority.get("evidence"), owner_id=owner_id, project_id=project.id)

    if action_type == ACTION_REFRESH_DOCUMENT_ANALYSIS:
        document_ref = next(
            (item for item in evidence if item.get("source_type") == "document" and item.get("source_id") is not None),
            None,
        )
        if document_ref is None:
            raise IntelligenceActionValidationError("This priority does not include an owned document to refresh.")
        document = _owned_document(int(document_ref["source_id"]), owner_id)
        if document.project_id is not None and int(document.project_id) != int(project.id):
            raise IntelligenceActionValidationError("The document is outside the selected project scope.")
        return (
            f"Refresh analysis: {document.filename}"[:255],
            reason or "The current saved document analysis is stale.",
            "document",
            int(document.id),
            {"document_id": int(document.id)},
            evidence,
            "medium",
        )

    if action_type == ACTION_CREATE_TASK:
        task_title = title
        for prefix in ("Review documented risk: ", "Review document action: ", "Refresh stale intelligence: "):
            if task_title.startswith(prefix):
                task_title = task_title[len(prefix):]
                task_title = f"Review: {task_title}"
                break
        task_title = _clean(task_title, 200) or "Review LifeOS priority"
        importance = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}.get(severity, "Medium")
        description_parts = [part for part in (reason, f"Suggested next step: {recommended}" if recommended else "") if part]
        return (
            f"Create task: {task_title}"[:255],
            reason or "LifeOS identified this as a current project priority.",
            "project",
            int(project.id),
            {
                "project_id": int(project.id),
                "title": task_title,
                "description": "\n\n".join(description_parts)[:4000] or None,
                "importance": importance,
            },
            evidence,
            "medium",
        )

    if action_type == ACTION_CREATE_NOTE:
        note_title = _clean(f"LifeOS insight: {title}", 255)
        body = "\n\n".join(
            part for part in (
                reason,
                f"Suggested next step: {recommended}" if recommended else "",
                f"Source priority: {title}",
            )
            if part
        )
        return (
            f"Save note: {title}"[:255],
            reason or "Save this verified LifeOS priority for later reference.",
            "project",
            int(project.id),
            {
                "project_id": int(project.id),
                "title": note_title,
                "content": body[:12000],
                "note_type": "Quick Note",
            },
            evidence,
            "low",
        )

    raise IntelligenceActionValidationError("This LifeOS action is not supported.")


def create_priority_action_proposal(
    *,
    owner_id: int,
    action_type: str,
    priority: dict[str, Any],
) -> LifeOSActionProposal:
    action_type = str(action_type or "").strip()
    if action_type not in ALLOWED_ACTION_TYPES:
        raise IntelligenceActionValidationError("This LifeOS action is not supported.")

    try:
        project_id = int(priority.get("project_id"))
    except (TypeError, ValueError) as error:
        raise IntelligenceActionValidationError("A valid project is required for this action.") from error
    project = _owned_project(project_id, owner_id)

    available = {item["type"] for item in priority_action_options(priority)}
    if action_type not in available:
        raise IntelligenceActionValidationError("That action is not allowed for this priority.")

    proposal_title, reason, target_type, target_id, payload, evidence, risk = _proposal_payload_from_priority(
        action_type=action_type,
        project=project,
        priority=priority,
        owner_id=owner_id,
    )
    proposal = LifeOSActionProposal(
        user_id=owner_id,
        action_type=action_type,
        status="pending",
        title=proposal_title,
        reason=reason,
        target_type=target_type,
        target_id=target_id,
        project_id=project.id,
        payload_json=json.dumps(payload, ensure_ascii=False),
        evidence_json=json.dumps(evidence, ensure_ascii=False),
        risk_level=risk,
        requires_confirmation=True,
    )
    try:
        db.session.add(proposal)
        db.session.commit()
        return proposal
    except SQLAlchemyError as error:
        db.session.rollback()
        raise IntelligenceActionExecutionError("LifeOS could not save the action proposal.") from error


def require_owned_proposal(*, proposal_id: int, owner_id: int) -> LifeOSActionProposal:
    proposal = LifeOSActionProposal.query.filter_by(id=proposal_id, user_id=owner_id).first()
    if proposal is None:
        raise IntelligenceActionNotFoundError("Action proposal not found.")
    return proposal


def proposal_to_dict(proposal: LifeOSActionProposal) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "action_type": proposal.action_type,
        "status": proposal.status,
        "title": proposal.title,
        "reason": proposal.reason,
        "target": {"type": proposal.target_type, "id": proposal.target_id},
        "project_id": proposal.project_id,
        "payload": proposal.payload,
        "evidence": proposal.evidence,
        "risk_level": proposal.risk_level,
        "requires_confirmation": bool(proposal.requires_confirmation),
        "execution": (
            {"resource_type": proposal.execution_resource_type, "resource_id": proposal.execution_resource_id}
            if proposal.execution_resource_type
            else None
        ),
        "failure_message": proposal.failure_message if proposal.status == "failed" else None,
        "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
        "resolved_at": proposal.resolved_at.isoformat() if proposal.resolved_at else None,
    }


def _mark_failed(proposal: LifeOSActionProposal, message: str) -> None:
    proposal.status = "failed"
    proposal.failure_message = _clean(message, 1000) or "The action could not be completed."
    proposal.resolved_at = datetime.utcnow()
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()


def _execute_confirmed_action(proposal: LifeOSActionProposal, owner_id: int) -> tuple[str, int]:
    payload = proposal.payload

    if proposal.action_type == ACTION_CREATE_TASK:
        project = _owned_project(int(payload.get("project_id")), owner_id)
        data = TaskInput(
            project_id=project.id,
            title=_clean(payload.get("title"), 200),
            description=_clean(payload.get("description"), 4000) or None,
            module=None,
            tags="LifeOS",
            importance=str(payload.get("importance") or "Medium"),
            difficulty="Medium",
            deadline=None,
            status="Pending",
            reminder_enabled=False,
            reminder_type="none",
            reminder_datetime=None,
            is_recurring=False,
            recurrence_type="none",
            recurrence_interval=1,
            recurrence_end_date=None,
            next_occurrence_date=None,
        )
        task = create_task(owner_id, data)
        return "task", int(task.id)

    if proposal.action_type == ACTION_CREATE_NOTE:
        project = _owned_project(int(payload.get("project_id")), owner_id)
        note = create_note(owner_id, NoteInput(
            title=_clean(payload.get("title"), 255),
            content=str(payload.get("content") or "")[:12000],
            note_type=str(payload.get("note_type") or "Quick Note"),
            project_id=project.id,
            is_pinned=False,
        ))
        return "note", int(note.id)

    if proposal.action_type == ACTION_REFRESH_DOCUMENT_ANALYSIS:
        document = _owned_document(int(payload.get("document_id")), owner_id)
        result = analyse_owned_document(document_id=document.id, user_id=owner_id, force=True)
        return "document_analysis", int(result.analysis.id)

    raise IntelligenceActionValidationError("This LifeOS action is not supported.")


def confirm_owned_action_proposal(*, proposal_id: int, owner_id: int) -> LifeOSActionProposal:
    proposal = require_owned_proposal(proposal_id=proposal_id, owner_id=owner_id)
    if proposal.status != "pending":
        raise IntelligenceActionValidationError("This action proposal is no longer waiting for confirmation.")

    # Persist the transition before executing.  Repeated/double-clicked confirm
    # requests cannot execute the same proposal twice.
    proposal.status = "executing"
    proposal.failure_message = None
    try:
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise IntelligenceActionExecutionError("LifeOS could not lock the action for execution.") from error

    try:
        resource_type, resource_id = _execute_confirmed_action(proposal, owner_id)
    except (IntelligenceActionError, TaskPersistenceError, NotePersistenceError, DocumentAnalysisWorkflowError, ValueError) as error:
        _mark_failed(proposal, str(error))
        raise IntelligenceActionExecutionError(str(error)) from error

    proposal.status = "confirmed"
    proposal.execution_resource_type = resource_type
    proposal.execution_resource_id = resource_id
    proposal.resolved_at = datetime.utcnow()

    # I13: preserve why confirmed AI-assisted work exists.  The connection
    # is deterministic and can only be created after this explicit user
    # confirmation; the model never writes graph edges itself.
    persist_confirmed_action_connections(
        proposal=proposal, resource_type=resource_type, resource_id=resource_id,
    )

    add_activity_event(
        user_id=owner_id,
        event_type="intelligence.action_confirmed",
        object_type=resource_type,
        object_id=resource_id,
        project_id=proposal.project_id,
        title=proposal.title.replace("Create task: ", "Created task: ").replace("Save note: ", "Saved note: ").replace("Refresh analysis: ", "Refreshed analysis: "),
        summary="The user confirmed a LifeOS intelligence action after reviewing its proposal.",
        changes={"action_type": proposal.action_type, "proposal_id": proposal.id},
        source_type="ask_lifeos",
        source_id=proposal.id,
    )
    try:
        db.session.commit()
        return proposal
    except SQLAlchemyError as error:
        db.session.rollback()
        raise IntelligenceActionExecutionError("The action completed, but LifeOS could not finalize its audit record.") from error


def dismiss_owned_action_proposal(*, proposal_id: int, owner_id: int) -> LifeOSActionProposal:
    proposal = require_owned_proposal(proposal_id=proposal_id, owner_id=owner_id)
    if proposal.status != "pending":
        raise IntelligenceActionValidationError("This action proposal is no longer waiting for confirmation.")
    proposal.status = "dismissed"
    proposal.resolved_at = datetime.utcnow()
    try:
        db.session.commit()
        return proposal
    except SQLAlchemyError as error:
        db.session.rollback()
        raise IntelligenceActionExecutionError("LifeOS could not dismiss the proposal.") from error

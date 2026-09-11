"""I10 — auditable workspace activity and deterministic "what changed?" views.

Activity is application state, not an LLM memory.  Mutation services append
small, structured events in the same database transaction where practical.
For resources created before I10, recent views also derive bounded events from
trusted timestamps so the feature is useful immediately after migration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import json
import re
from typing import Any, Iterable

from database import db
from models import (
    Document,
    DocumentAIAnalysis,
    LifeOSActivityEvent,
    Note,
    Project,
    Task,
)


MAX_ACTIVITY_ITEMS = 30
MAX_ACTIVITY_WINDOW_DAYS = 30


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k)[:80]: _json_safe(v) for k, v in list(value.items())[:30]}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in list(value)[:30]]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def add_activity_event(
    *,
    user_id: int,
    event_type: str,
    object_type: str,
    object_id: int | None,
    title: str,
    summary: str | None = None,
    project_id: int | None = None,
    changes: dict[str, Any] | None = None,
    source_type: str = "user",
    source_id: int | None = None,
    created_at: datetime | None = None,
) -> LifeOSActivityEvent:
    """Append an activity event without committing the caller's transaction."""

    event = LifeOSActivityEvent(
        user_id=int(user_id),
        event_type=str(event_type or "activity")[:80],
        object_type=str(object_type or "workspace")[:64],
        object_id=int(object_id) if object_id is not None else None,
        project_id=int(project_id) if project_id is not None else None,
        title=" ".join(str(title or "LifeOS activity").split())[:255],
        summary=(" ".join(str(summary).split())[:2000] if summary else None),
        changes_json=json.dumps(_json_safe(changes or {}), ensure_ascii=False),
        source_type=str(source_type or "user")[:64],
        source_id=int(source_id) if source_id is not None else None,
        created_at=created_at or datetime.utcnow(),
    )
    db.session.add(event)
    return event


@dataclass(frozen=True)
class RecentActivityItem:
    event_type: str
    object_type: str
    object_id: int | None
    project_id: int | None
    project_title: str | None
    title: str
    summary: str | None
    occurred_at: datetime
    source: str
    changes: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "project_id": self.project_id,
            "project_title": self.project_title,
            "title": self.title,
            "summary": self.summary,
            "occurred_at": self.occurred_at.isoformat(),
            "source": self.source,
            "changes": self.changes,
        }


@dataclass(frozen=True)
class RecentActivityResult:
    start_at: datetime
    end_at: datetime
    window_label: str
    project_id: int | None
    project_title: str | None
    items: tuple[RecentActivityItem, ...]
    total_items: int
    context_limited: bool

    @property
    def summary(self) -> str:
        scope = self.project_title or "your workspace"
        if not self.items:
            return f"I did not find a meaningful recorded change in {scope} during {self.window_label}."
        lead = self.items[0]
        count = self.total_items
        text = (
            f"I found {count} meaningful change{'s' if count != 1 else ''} in {scope} "
            f"during {self.window_label}. Most recent: {lead.title}."
        )
        if self.context_limited:
            text += f" I am showing the newest {len(self.items)} changes."
        return text

    def to_dict(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for item in self.items:
            counts[item.object_type] = counts.get(item.object_type, 0) + 1
        return {
            "window": {
                "start_at": self.start_at.isoformat(),
                "end_at": self.end_at.isoformat(),
                "label": self.window_label,
            },
            "scope": (
                {"type": "project", "id": self.project_id, "label": self.project_title}
                if self.project_id is not None
                else {"type": "workspace", "id": None, "label": "All workspace"}
            ),
            "summary": self.summary,
            "items": [item.to_dict() for item in self.items],
            "counts": counts,
            "total_items": self.total_items,
            "context_limited": self.context_limited,
            "verified_from_state": True,
            "read_only": True,
        }


def _project_lookup(owner_id: int) -> dict[int, str]:
    return {
        int(project.id): str(project.title or f"Project {project.id}")
        for project in Project.query.filter_by(user_id=owner_id).all()
    }


def _event_item(event: LifeOSActivityEvent, projects: dict[int, str]) -> RecentActivityItem:
    return RecentActivityItem(
        event_type=event.event_type,
        object_type=event.object_type,
        object_id=event.object_id,
        project_id=event.project_id,
        project_title=projects.get(int(event.project_id)) if event.project_id is not None else None,
        title=event.title,
        summary=event.summary,
        occurred_at=event.created_at,
        source="activity_log",
        changes=event.changes,
    )


def _derived_item(
    *,
    event_type: str,
    object_type: str,
    object_id: int | None,
    project_id: int | None,
    project_title: str | None,
    title: str,
    summary: str | None,
    occurred_at: datetime,
    changes: dict[str, Any] | None = None,
) -> RecentActivityItem:
    return RecentActivityItem(
        event_type=event_type,
        object_type=object_type,
        object_id=object_id,
        project_id=project_id,
        project_title=project_title,
        title=title,
        summary=summary,
        occurred_at=occurred_at,
        source="derived_state",
        changes=changes or {},
    )


def _within(value: datetime | None, start_at: datetime, end_at: datetime) -> bool:
    return bool(value and start_at <= value <= end_at)


def _derive_pre_i10_activity(
    *,
    owner_id: int,
    start_at: datetime,
    end_at: datetime,
    project_id: int | None,
    projects: dict[int, str],
) -> list[RecentActivityItem]:
    """Use trusted timestamps to backfill useful recent context after migration."""

    items: list[RecentActivityItem] = []

    project_query = Project.query.filter_by(user_id=owner_id)
    if project_id is not None:
        project_query = project_query.filter(Project.id == project_id)
    for project in project_query.all():
        label = projects.get(int(project.id), project.title)
        if _within(project.created_at, start_at, end_at):
            items.append(_derived_item(
                event_type="project.created", object_type="project", object_id=project.id,
                project_id=project.id, project_title=label,
                title=f"Project created: {project.title}", summary=None,
                occurred_at=project.created_at,
            ))
        if (
            _within(project.updated_at, start_at, end_at)
            and project.updated_at
            and project.created_at
            and abs((project.updated_at - project.created_at).total_seconds()) > 60
        ):
            items.append(_derived_item(
                event_type="project.updated", object_type="project", object_id=project.id,
                project_id=project.id, project_title=label,
                title=f"Project updated: {project.title}",
                summary="Current project state was updated.", occurred_at=project.updated_at,
            ))

    task_query = Task.query.filter_by(user_id=owner_id)
    if project_id is not None:
        task_query = task_query.filter(Task.project_id == project_id)
    for task in task_query.all():
        label = projects.get(int(task.project_id)) if task.project_id is not None else None
        if _within(task.created_at, start_at, end_at):
            items.append(_derived_item(
                event_type="task.created", object_type="task", object_id=task.id,
                project_id=task.project_id, project_title=label,
                title=f"Task created: {task.title}",
                summary=f"Status: {task.status}.", occurred_at=task.created_at,
            ))
        if _within(task.completed_at, start_at, end_at):
            items.append(_derived_item(
                event_type="task.completed", object_type="task", object_id=task.id,
                project_id=task.project_id, project_title=label,
                title=f"Task completed: {task.title}", summary=None,
                occurred_at=task.completed_at,
            ))

    note_query = Note.query.filter_by(user_id=owner_id)
    if project_id is not None:
        note_query = note_query.filter(Note.project_id == project_id)
    for note in note_query.all():
        label = projects.get(int(note.project_id)) if note.project_id is not None else None
        if _within(note.created_at, start_at, end_at):
            items.append(_derived_item(
                event_type="note.created", object_type="note", object_id=note.id,
                project_id=note.project_id, project_title=label,
                title=f"Note created: {note.title}", summary=None,
                occurred_at=note.created_at,
            ))
        if (
            _within(note.updated_at, start_at, end_at)
            and note.updated_at
            and note.created_at
            and abs((note.updated_at - note.created_at).total_seconds()) > 60
        ):
            items.append(_derived_item(
                event_type="note.updated", object_type="note", object_id=note.id,
                project_id=note.project_id, project_title=label,
                title=f"Note updated: {note.title}", summary=None,
                occurred_at=note.updated_at,
            ))

    document_query = Document.query.filter(Document.user_id == owner_id)
    if project_id is not None:
        document_query = document_query.filter(Document.project_id == project_id)
    documents = document_query.all()
    document_ids = [int(item.id) for item in documents]
    by_document_id = {int(item.id): item for item in documents}
    for document in documents:
        label = projects.get(int(document.project_id)) if document.project_id is not None else None
        if _within(document.uploaded_at, start_at, end_at):
            event_type = "document.version_uploaded" if int(document.version_number or 0) > 1 else "document.uploaded"
            items.append(_derived_item(
                event_type=event_type, object_type="document", object_id=document.id,
                project_id=document.project_id, project_title=label,
                title=(
                    f"New document version: {document.filename}"
                    if event_type == "document.version_uploaded"
                    else f"Document uploaded: {document.filename}"
                ),
                summary=(f"Version {document.version_number}." if document.version_number else None),
                occurred_at=document.uploaded_at,
            ))

    if document_ids:
        analyses = (
            DocumentAIAnalysis.query
            .filter(
                DocumentAIAnalysis.user_id == owner_id,
                DocumentAIAnalysis.document_id.in_(document_ids),
                DocumentAIAnalysis.created_at >= start_at,
                DocumentAIAnalysis.created_at <= end_at,
            )
            .all()
        )
        for analysis in analyses:
            document = by_document_id.get(int(analysis.document_id))
            if document is None:
                continue
            label = projects.get(int(document.project_id)) if document.project_id is not None else None
            completed = str(analysis.status or "").casefold() == "completed"
            items.append(_derived_item(
                event_type="document.analysis_completed" if completed else "document.analysis_failed",
                object_type="document_analysis", object_id=analysis.id,
                project_id=document.project_id, project_title=label,
                title=(
                    f"Document analysis completed: {document.filename}"
                    if completed else f"Document analysis failed: {document.filename}"
                ),
                summary=None,
                occurred_at=analysis.created_at,
            ))

    return items


def _deduplicate(
    logged: Iterable[RecentActivityItem],
    derived: Iterable[RecentActivityItem],
) -> list[RecentActivityItem]:
    logged_items = list(logged)
    domain_objects = {
        (item.object_type, item.object_id)
        for item in logged_items
        if item.event_type != "intelligence.action_confirmed"
    }
    # The confirmed-action audit remains persisted, but the user-facing recent
    # timeline should not show both "Task created" and "Created task" for the
    # same write.
    result = [
        item for item in logged_items
        if not (
            item.event_type == "intelligence.action_confirmed"
            and (item.object_type, item.object_id) in domain_objects
        )
    ]
    logged_keys = {
        (item.event_type, item.object_type, item.object_id)
        for item in result
    }
    versioned_document_ids = {
        item.object_id for item in result
        if item.event_type == "document.version_changed" and item.object_type == "document"
    }
    for item in derived:
        key = (item.event_type, item.object_type, item.object_id)
        if (
            item.object_type == "document"
            and item.object_id in versioned_document_ids
            and item.event_type in {"document.uploaded", "document.version_uploaded"}
        ):
            continue
        if key not in logged_keys:
            result.append(item)
    result.sort(key=lambda item: (item.occurred_at, item.object_id or 0), reverse=True)
    return result


def activity_window_from_query(query: str, *, now: datetime | None = None) -> tuple[datetime, datetime, str]:
    current = now or datetime.utcnow()
    text = " ".join(str(query or "").casefold().split())
    end_at = current

    if "yesterday" in text:
        day = current.date() - timedelta(days=1)
        return datetime.combine(day, time.min), datetime.combine(day, time.max), "yesterday"
    if "today" in text:
        day = current.date()
        return datetime.combine(day, time.min), current, "today"
    if "this week" in text:
        day = current.date()
        monday = day - timedelta(days=day.weekday())
        return datetime.combine(monday, time.min), current, "this week"

    match = re.search(r"(?:last|past)\s+(\d{1,2})\s+days?", text)
    if match:
        days = max(1, min(int(match.group(1)), MAX_ACTIVITY_WINDOW_DAYS))
        return current - timedelta(days=days), end_at, f"the last {days} days"

    return current - timedelta(days=7), end_at, "the last 7 days"


def build_owned_recent_activity(
    *,
    owner_id: int,
    query: str = "",
    project_id: int | None = None,
    now: datetime | None = None,
    limit: int = MAX_ACTIVITY_ITEMS,
) -> RecentActivityResult:
    start_at, end_at, window_label = activity_window_from_query(query, now=now)
    projects = _project_lookup(owner_id)

    if project_id is not None and int(project_id) not in projects:
        # Neutral ownership boundary: caller should translate into not-found.
        raise LookupError("Project not found")

    query_obj = LifeOSActivityEvent.query.filter(
        LifeOSActivityEvent.user_id == owner_id,
        LifeOSActivityEvent.created_at >= start_at,
        LifeOSActivityEvent.created_at <= end_at,
    )
    if project_id is not None:
        query_obj = query_obj.filter(LifeOSActivityEvent.project_id == project_id)
    logged = [_event_item(item, projects) for item in query_obj.order_by(LifeOSActivityEvent.created_at.desc(), LifeOSActivityEvent.id.desc()).all()]

    derived = _derive_pre_i10_activity(
        owner_id=owner_id,
        start_at=start_at,
        end_at=end_at,
        project_id=project_id,
        projects=projects,
    )
    combined = _deduplicate(logged, derived)
    bounded_limit = max(1, min(int(limit or MAX_ACTIVITY_ITEMS), MAX_ACTIVITY_ITEMS))
    selected = tuple(combined[:bounded_limit])
    return RecentActivityResult(
        start_at=start_at,
        end_at=end_at,
        window_label=window_label,
        project_id=project_id,
        project_title=projects.get(int(project_id)) if project_id is not None else None,
        items=selected,
        total_items=len(combined),
        context_limited=len(combined) > len(selected),
    )

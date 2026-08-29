"""I14 — normalized, ownership-bounded LifeOS event engine.

The engine turns trusted application state + I10 activity into a small event
stream that future proactive features can consume. It does not invoke an LLM,
does not run arbitrary tools, and never mutates workspace resources.

V1 is deliberately scan-based: the web client refreshes it while LifeOS is
open and a CLI can run it on demand. A later scheduler/automation layer can
call the same service without changing event semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
from typing import Any

from database import db
from models import (
    LifeOSActivityEvent,
    LifeOSIntelligenceEvent,
    Project,
    Task,
)
from services.intelligence_workspace_query_service import build_owned_document_review_insight


EVENT_SCAN_ACTIVITY_HOURS = 48
DEADLINE_APPROACHING_DAYS = 3
MAX_EVENT_RESULTS = 100

STATE_EVENT_TYPES = {
    "task.overdue",
    "task.blocked",
    "deadline.approaching",
    "project.overdue",
    "project.deadline_approaching",
    "document.intelligence_stale",
    "document.analysis_missing",
}

# I10 already records these at the mutation boundary. I14 normalizes them so
# downstream consumers do not need to understand every feature service.
ACTIVITY_EVENT_TYPES = {
    "task.created",
    "task.updated",
    "task.completed",
    "task.reopened",
    "task.deleted",
    "project.created",
    "project.updated",
    "project.deleted",
    "note.created",
    "note.updated",
    "note.deleted",
    "document.version_changed",
    "document.analysis_completed",
    "intelligence.action_confirmed",
}


@dataclass(frozen=True)
class EventSpec:
    event_type: str
    severity: str
    lifecycle: str
    object_type: str
    object_id: int | None
    project_id: int | None
    title: str
    summary: str | None
    dedupe_key: str
    context: dict[str, Any]
    source_type: str
    source_id: int | None
    occurred_at: datetime | None = None


@dataclass(frozen=True)
class IntelligenceEventScanResult:
    events: tuple[LifeOSIntelligenceEvent, ...]
    new_count: int
    refreshed_count: int
    resolved_count: int
    open_count: int
    scanned_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [event_to_dict(event) for event in self.events],
            "counts": {
                "returned": len(self.events),
                "new": self.new_count,
                "refreshed": self.refreshed_count,
                "resolved": self.resolved_count,
                "open": self.open_count,
            },
            "scanned_at": self.scanned_at.isoformat(),
            "verified_from_state": True,
            "read_only_workspace": True,
        }


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


def event_to_dict(event: LifeOSIntelligenceEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "severity": event.severity,
        "lifecycle": event.lifecycle,
        "object_type": event.object_type,
        "object_id": event.object_id,
        "project_id": event.project_id,
        "title": event.title,
        "summary": event.summary,
        "context": event.context,
        "source_type": event.source_type,
        "source_id": event.source_id,
        "detected_at": event.detected_at.isoformat() if event.detected_at else None,
        "last_seen_at": event.last_seen_at.isoformat() if event.last_seen_at else None,
        "resolved_at": event.resolved_at.isoformat() if event.resolved_at else None,
    }


def _is_complete(status: str | None) -> bool:
    return str(status or "").strip().casefold() in {"completed", "complete", "done", "archived"}


def _is_blocked(status: str | None) -> bool:
    return str(status or "").strip().casefold() in {"blocked", "stuck", "waiting", "on hold", "on_hold"}


def _project_titles(owner_id: int) -> dict[int, str]:
    return {
        int(project.id): str(project.title or f"Project {project.id}")
        for project in Project.query.filter(Project.user_id == owner_id).all()
    }


def _task_state_specs(*, owner_id: int, today: date, projects: dict[int, str]) -> list[EventSpec]:
    specs: list[EventSpec] = []
    tasks = Task.query.filter(Task.user_id == owner_id).all()
    for task in tasks:
        if _is_complete(task.status):
            continue
        project_title = projects.get(int(task.project_id)) if task.project_id is not None else None
        scope = project_title or "General Workspace"

        if _is_blocked(task.status):
            specs.append(EventSpec(
                event_type="task.blocked",
                severity="high",
                lifecycle="open",
                object_type="task",
                object_id=task.id,
                project_id=task.project_id,
                title=f"Blocked task: {task.title}",
                summary=f"{task.title} is currently blocked in {scope}.",
                dedupe_key=f"state:task.blocked:task:{task.id}",
                context={"status": task.status, "project_title": project_title},
                source_type="state_scan",
                source_id=task.id,
            ))

        if task.deadline:
            days = (task.deadline - today).days
            if days < 0:
                specs.append(EventSpec(
                    event_type="task.overdue",
                    severity="high",
                    lifecycle="open",
                    object_type="task",
                    object_id=task.id,
                    project_id=task.project_id,
                    title=f"Overdue task: {task.title}",
                    summary=f"{task.title} was due {task.deadline.isoformat()} in {scope}.",
                    dedupe_key=f"state:task.overdue:task:{task.id}:due:{task.deadline.isoformat()}",
                    context={"deadline": task.deadline.isoformat(), "days_overdue": abs(days), "status": task.status, "project_title": project_title},
                    source_type="state_scan",
                    source_id=task.id,
                ))
            elif days <= DEADLINE_APPROACHING_DAYS:
                label = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
                specs.append(EventSpec(
                    event_type="deadline.approaching",
                    severity="medium" if days <= 1 else "normal",
                    lifecycle="open",
                    object_type="task",
                    object_id=task.id,
                    project_id=task.project_id,
                    title=f"Task deadline {label}: {task.title}",
                    summary=f"{task.title} is due {task.deadline.isoformat()} in {scope}.",
                    dedupe_key=f"state:deadline.approaching:task:{task.id}:due:{task.deadline.isoformat()}",
                    context={"deadline": task.deadline.isoformat(), "days_until": days, "status": task.status, "project_title": project_title},
                    source_type="state_scan",
                    source_id=task.id,
                ))
    return specs


def _project_state_specs(*, owner_id: int, today: date) -> list[EventSpec]:
    specs: list[EventSpec] = []
    for project in Project.query.filter(Project.user_id == owner_id).all():
        if _is_complete(project.status) or not project.deadline:
            continue
        days = (project.deadline - today).days
        if days < 0:
            specs.append(EventSpec(
                event_type="project.overdue",
                severity="high",
                lifecycle="open",
                object_type="project",
                object_id=project.id,
                project_id=project.id,
                title=f"Project deadline passed: {project.title}",
                summary=f"{project.title} was due {project.deadline.isoformat()} and is still {project.status or 'active'}.",
                dedupe_key=f"state:project.overdue:project:{project.id}:due:{project.deadline.isoformat()}",
                context={"deadline": project.deadline.isoformat(), "days_overdue": abs(days), "status": project.status, "progress": project.progress},
                source_type="state_scan",
                source_id=project.id,
            ))
        elif days <= DEADLINE_APPROACHING_DAYS:
            label = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
            specs.append(EventSpec(
                event_type="project.deadline_approaching",
                severity="medium" if days <= 1 else "normal",
                lifecycle="open",
                object_type="project",
                object_id=project.id,
                project_id=project.id,
                title=f"Project deadline {label}: {project.title}",
                summary=f"{project.title} is due {project.deadline.isoformat()} with {int(project.progress or 0)}% saved progress.",
                dedupe_key=f"state:project.deadline_approaching:project:{project.id}:due:{project.deadline.isoformat()}",
                context={"deadline": project.deadline.isoformat(), "days_until": days, "status": project.status, "progress": project.progress},
                source_type="state_scan",
                source_id=project.id,
            ))
    return specs


def _document_state_specs(*, owner_id: int) -> list[EventSpec]:
    specs: list[EventSpec] = []
    insight = build_owned_document_review_insight(owner_id=owner_id)
    for item in insight.items:
        if item.source_id is None:
            continue
        status = str(item.status or "")
        if status == "Stale":
            event_type = "document.intelligence_stale"
            severity = "medium"
            title = f"Document intelligence is stale: {item.title}"
            summary = "The current document changed after its saved structured analysis. Refresh before relying on the old findings."
        elif status == "Not analysed":
            event_type = "document.analysis_missing"
            severity = "normal"
            title = f"Document has no structured analysis: {item.title}"
            summary = "This current document can be searched with Document Brain, but it does not yet have completed structured analysis."
        else:
            continue
        specs.append(EventSpec(
            event_type=event_type,
            severity=severity,
            lifecycle="open",
            object_type="document",
            object_id=item.source_id,
            project_id=item.project_id,
            title=title,
            summary=summary,
            dedupe_key=f"state:{event_type}:document:{item.source_id}",
            context={"analysis_status": status, "project_title": item.project_title},
            source_type="state_scan",
            source_id=item.source_id,
        ))
    return specs


def _activity_specs(*, owner_id: int, now: datetime) -> list[EventSpec]:
    cutoff = now - timedelta(hours=EVENT_SCAN_ACTIVITY_HOURS)
    rows = (
        LifeOSActivityEvent.query
        .filter(
            LifeOSActivityEvent.user_id == owner_id,
            LifeOSActivityEvent.created_at >= cutoff,
            LifeOSActivityEvent.event_type.in_(tuple(ACTIVITY_EVENT_TYPES)),
        )
        .order_by(LifeOSActivityEvent.created_at.asc(), LifeOSActivityEvent.id.asc())
        .all()
    )
    specs: list[EventSpec] = []
    for row in rows:
        severity = "normal"
        if row.event_type in {"document.version_changed"}:
            severity = "medium"
        elif row.event_type in {"document.analysis_completed", "intelligence.action_confirmed", "task.completed"}:
            severity = "info"
        specs.append(EventSpec(
            event_type=row.event_type,
            severity=severity,
            lifecycle="observed",
            object_type=row.object_type,
            object_id=row.object_id,
            project_id=row.project_id,
            title=row.title,
            summary=row.summary,
            dedupe_key=f"activity:{row.id}:{row.event_type}",
            context={"changes": row.changes},
            source_type="activity",
            source_id=row.id,
            occurred_at=row.created_at,
        ))
    return specs


def _upsert_spec(*, owner_id: int, spec: EventSpec, now: datetime) -> tuple[LifeOSIntelligenceEvent, bool]:
    event = LifeOSIntelligenceEvent.query.filter_by(user_id=owner_id, dedupe_key=spec.dedupe_key).first()
    created = event is None
    if event is None:
        event = LifeOSIntelligenceEvent(
            user_id=owner_id,
            dedupe_key=spec.dedupe_key,
            detected_at=spec.occurred_at or now,
        )
        db.session.add(event)

    event.event_type = spec.event_type
    event.severity = spec.severity
    event.lifecycle = spec.lifecycle
    event.object_type = spec.object_type
    event.object_id = spec.object_id
    event.project_id = spec.project_id
    event.title = " ".join(str(spec.title or "LifeOS event").split())[:255]
    event.summary = " ".join(str(spec.summary).split())[:2000] if spec.summary else None
    event.context_json = json.dumps(_json_safe(spec.context), ensure_ascii=False)
    event.source_type = spec.source_type
    event.source_id = spec.source_id
    event.last_seen_at = now
    if spec.lifecycle == "open":
        event.resolved_at = None
    return event, created


def scan_owned_intelligence_events(
    *,
    owner_id: int,
    today: date | None = None,
    now: datetime | None = None,
    limit: int = MAX_EVENT_RESULTS,
) -> IntelligenceEventScanResult:
    """Detect current events, persist only normalized metadata, resolve stale state signals."""

    effective_now = now or datetime.utcnow()
    # Deadlines are date-only workspace values, so evaluate them against the
    # server/local calendar date rather than UTC.  Using effective_now.date()
    # makes a task due yesterday look merely due today for users east of UTC
    # during the local-midnight/UTC-midnight gap.
    effective_today = today or date.today()
    projects = _project_titles(owner_id)

    state_specs = (
        _task_state_specs(owner_id=owner_id, today=effective_today, projects=projects)
        + _project_state_specs(owner_id=owner_id, today=effective_today)
        + _document_state_specs(owner_id=owner_id)
    )
    occurrence_specs = _activity_specs(owner_id=owner_id, now=effective_now)
    specs = state_specs + occurrence_specs

    active_state_keys = {spec.dedupe_key for spec in state_specs}
    new_count = 0
    refreshed_count = 0
    for spec in specs:
        _, created = _upsert_spec(owner_id=owner_id, spec=spec, now=effective_now)
        if created:
            new_count += 1
        else:
            refreshed_count += 1

    resolved_count = 0
    open_state_events = LifeOSIntelligenceEvent.query.filter(
        LifeOSIntelligenceEvent.user_id == owner_id,
        LifeOSIntelligenceEvent.event_type.in_(tuple(STATE_EVENT_TYPES)),
        LifeOSIntelligenceEvent.lifecycle == "open",
    ).all()
    for event in open_state_events:
        if event.dedupe_key not in active_state_keys:
            event.lifecycle = "resolved"
            event.resolved_at = effective_now
            event.last_seen_at = effective_now
            resolved_count += 1

    db.session.commit()

    bounded_limit = max(1, min(int(limit or MAX_EVENT_RESULTS), MAX_EVENT_RESULTS))
    events = tuple(
        LifeOSIntelligenceEvent.query
        .filter(LifeOSIntelligenceEvent.user_id == owner_id)
        .order_by(LifeOSIntelligenceEvent.detected_at.desc(), LifeOSIntelligenceEvent.id.desc())
        .limit(bounded_limit)
        .all()
    )
    open_count = LifeOSIntelligenceEvent.query.filter_by(user_id=owner_id, lifecycle="open").count()
    return IntelligenceEventScanResult(
        events=events,
        new_count=new_count,
        refreshed_count=refreshed_count,
        resolved_count=resolved_count,
        open_count=open_count,
        scanned_at=effective_now,
    )


def list_owned_intelligence_events(
    *,
    owner_id: int,
    lifecycle: str | None = None,
    limit: int = 50,
) -> tuple[LifeOSIntelligenceEvent, ...]:
    query = LifeOSIntelligenceEvent.query.filter(LifeOSIntelligenceEvent.user_id == owner_id)
    if lifecycle:
        query = query.filter(LifeOSIntelligenceEvent.lifecycle == lifecycle)
    bounded = max(1, min(int(limit or 50), MAX_EVENT_RESULTS))
    return tuple(query.order_by(LifeOSIntelligenceEvent.detected_at.desc(), LifeOSIntelligenceEvent.id.desc()).limit(bounded).all())

"""I15 — proactive, in-app intelligence built on I14 events.

I15 notices attention-worthy changes without waiting for an Ask LifeOS prompt.
It is intentionally non-autonomous: notices may link to a resource or prefill an
Ask LifeOS question, but they never execute an I9 action or mutate workspace
state. The browser refreshes this service periodically while LifeOS is open.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from database import db
from models import LifeOSIntelligenceEvent, LifeOSProactiveNotification
from services.intelligence_event_service import scan_owned_intelligence_events
from services.structured_memory_service import (
    has_active_dismissed_suggestion,
    remember_dismissed_suggestion,
)


MAX_PROACTIVE_NOTIFICATIONS = 50
NOTIFY_EVENT_TYPES = {
    "task.overdue",
    "task.blocked",
    "deadline.approaching",
    "project.overdue",
    "project.deadline_approaching",
    "document.intelligence_stale",
    "document.analysis_completed",
    # I17 automated intelligence results. These are notification metadata only;
    # automation execution still cannot mutate workspace resources.
    "automation.today_briefing_ready",
    "automation.weekly_review_ready",
    "automation.project_review_ready",
    "automation.project_risk_escalated",
    "automation.unhandled_followup",
    "automation.event_context_ready",
}


class ProactiveNotificationNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class ProactiveNotificationResult:
    items: tuple[LifeOSProactiveNotification, ...]
    unread_count: int
    created_count: int = 0
    resolved_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [notification_to_dict(item) for item in self.items],
            "counts": {
                "unread": self.unread_count,
                "returned": len(self.items),
                "created": self.created_count,
                "resolved": self.resolved_count,
            },
            "verified_from_state": True,
            "workspace_mutation": False,
            "delivery": "in_app",
        }


def _action_for_event(event: LifeOSIntelligenceEvent) -> tuple[str | None, str | None, str | None]:
    if event.event_type.startswith("automation."):
        context = event.context or {}
        label = str(context.get("action_label") or "Open Automations").strip() or "Open Automations"
        href = str(context.get("action_href") or "/automations").strip() or "/automations"
        ask_query = str(context.get("ask_query") or "").strip() or None
        return label[:80], href[:500], ask_query[:1000] if ask_query else None
    if event.object_type == "document" and event.object_id:
        if event.event_type in {"document.intelligence_stale", "document.analysis_missing", "document.analysis_completed"}:
            return "Open document", f"/documents/{event.object_id}", f"Review document #{event.object_id} and tell me what needs attention"
    if event.object_type == "project" and event.object_id:
        return "Open project", f"/projects/{event.object_id}", f"Review my project #{event.object_id} and tell me what needs attention"
    if event.object_type == "task":
        return "Open tasks", "/tasks", "What should I do about my overdue or blocked tasks?"
    return "Ask LifeOS", "/ask", None


def _category(event_type: str) -> str:
    if event_type.startswith("automation."):
        return "automation_intelligence"
    if event_type.startswith("task.") or event_type.startswith("deadline."):
        return "task_attention"
    if event_type.startswith("project."):
        return "project_attention"
    if event_type.startswith("document."):
        return "document_attention"
    if event_type.startswith("intelligence."):
        return "lifeos_action"
    return "attention"


def notification_to_dict(item: LifeOSProactiveNotification) -> dict[str, Any]:
    event = item.event
    return {
        "id": item.id,
        "event_id": item.event_id,
        "event_type": event.event_type if event else None,
        "category": item.category,
        "severity": item.severity,
        "status": item.status,
        "title": item.title,
        "message": item.message,
        "action": {
            "label": item.action_label,
            "href": item.action_href,
            "ask_query": item.ask_query,
        },
        "resource": {
            "type": event.object_type if event else None,
            "id": event.object_id if event else None,
            "project_id": event.project_id if event else None,
        },
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "read_at": item.read_at.isoformat() if item.read_at else None,
        "dismissed_at": item.dismissed_at.isoformat() if item.dismissed_at else None,
        "verified_from_state": True,
    }


def _owned_notification(*, owner_id: int, notification_id: int) -> LifeOSProactiveNotification:
    item = LifeOSProactiveNotification.query.filter_by(id=notification_id, user_id=owner_id).first()
    if item is None:
        raise ProactiveNotificationNotFoundError("Notification not found")
    return item


def _list(*, owner_id: int, limit: int = 20, include_dismissed: bool = False) -> tuple[LifeOSProactiveNotification, ...]:
    query = LifeOSProactiveNotification.query.filter(LifeOSProactiveNotification.user_id == owner_id)
    if not include_dismissed:
        query = query.filter(LifeOSProactiveNotification.status != "dismissed")
    bounded = max(1, min(int(limit or 20), MAX_PROACTIVE_NOTIFICATIONS))
    return tuple(query.order_by(LifeOSProactiveNotification.created_at.desc(), LifeOSProactiveNotification.id.desc()).limit(bounded).all())


def list_owned_proactive_notifications(*, owner_id: int, limit: int = 20) -> ProactiveNotificationResult:
    items = _list(owner_id=owner_id, limit=limit)
    unread_count = LifeOSProactiveNotification.query.filter_by(user_id=owner_id, status="unread").count()
    return ProactiveNotificationResult(items=items, unread_count=unread_count)


def refresh_owned_proactive_notifications(
    *,
    owner_id: int,
    now: datetime | None = None,
    limit: int = 20,
) -> ProactiveNotificationResult:
    """Scan I14 and materialize idempotent, in-app I15 notices."""

    effective_now = now or datetime.utcnow()
    scan_owned_intelligence_events(owner_id=owner_id, now=effective_now)

    base_query = LifeOSIntelligenceEvent.query.filter(
        LifeOSIntelligenceEvent.user_id == owner_id,
        LifeOSIntelligenceEvent.event_type.in_(tuple(NOTIFY_EVENT_TYPES)),
    )
    open_events = base_query.filter(LifeOSIntelligenceEvent.lifecycle == "open").all()
    recent_observed = base_query.filter(
        LifeOSIntelligenceEvent.lifecycle == "observed",
        LifeOSIntelligenceEvent.detected_at >= effective_now - timedelta(days=7),
    ).all()

    created_count = 0
    for event in open_events + recent_observed:
        item = LifeOSProactiveNotification.query.filter_by(user_id=owner_id, event_id=event.id).first()
        if item is None and has_active_dismissed_suggestion(owner_id=owner_id, event=event, now=effective_now):
            continue
        if item is not None:
            # An observed event is immutable; an open event can evolve in text/severity.
            if item.status == "resolved" and event.lifecycle == "open":
                item.status = "unread"
                item.read_at = None
            item.severity = event.severity
            item.title = event.title
            item.message = event.summary or event.title
            continue

        action_label, action_href, ask_query = _action_for_event(event)
        item = LifeOSProactiveNotification(
            user_id=owner_id,
            event_id=event.id,
            category=_category(event.event_type),
            severity=event.severity,
            status="unread",
            title=event.title,
            message=event.summary or event.title,
            action_label=action_label,
            action_href=action_href,
            ask_query=ask_query,
            created_at=effective_now,
            updated_at=effective_now,
        )
        db.session.add(item)
        created_count += 1

    resolved_event_ids = [
        int(event.id)
        for event in LifeOSIntelligenceEvent.query.filter_by(user_id=owner_id, lifecycle="resolved").all()
    ]
    resolved_count = 0
    if resolved_event_ids:
        for item in LifeOSProactiveNotification.query.filter(
            LifeOSProactiveNotification.user_id == owner_id,
            LifeOSProactiveNotification.event_id.in_(resolved_event_ids),
            LifeOSProactiveNotification.status.in_(("unread", "read")),
        ).all():
            item.status = "resolved"
            item.updated_at = effective_now
            resolved_count += 1

    db.session.commit()
    result = list_owned_proactive_notifications(owner_id=owner_id, limit=limit)
    return ProactiveNotificationResult(
        items=result.items,
        unread_count=result.unread_count,
        created_count=created_count,
        resolved_count=resolved_count,
    )


def mark_owned_proactive_notification_read(*, owner_id: int, notification_id: int) -> LifeOSProactiveNotification:
    item = _owned_notification(owner_id=owner_id, notification_id=notification_id)
    if item.status == "unread":
        item.status = "read"
        item.read_at = datetime.utcnow()
        db.session.commit()
    return item


def dismiss_owned_proactive_notification(*, owner_id: int, notification_id: int) -> LifeOSProactiveNotification:
    item = _owned_notification(owner_id=owner_id, notification_id=notification_id)
    now = datetime.utcnow()
    item.status = "dismissed"
    item.dismissed_at = now
    remember_dismissed_suggestion(owner_id=owner_id, notification=item, now=now)
    db.session.commit()
    return item


def mark_all_owned_proactive_notifications_read(*, owner_id: int) -> int:
    now = datetime.utcnow()
    items = LifeOSProactiveNotification.query.filter_by(user_id=owner_id, status="unread").all()
    for item in items:
        item.status = "read"
        item.read_at = now
    if items:
        db.session.commit()
    return len(items)

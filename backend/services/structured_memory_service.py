"""I16 — controlled, inspectable structured memory for LifeOS Intelligence.

Memory is deliberately small and typed.  It is not a hidden transcript and it
never stores raw document text, model prompts, API keys, passwords, or arbitrary
chat history.  Users can inspect and delete every persisted memory row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import re
from typing import Any

from sqlalchemy import or_

from database import db
from models import LifeOSMemory, LifeOSActivityEvent, Project


MEMORY_TYPES = {"preference", "current_focus", "recent_project", "dismissed_suggestion"}
USER_WRITABLE_TYPES = {"preference", "current_focus"}
MAX_MEMORY_VALUE_CHARACTERS = 500
MAX_MEMORY_LABEL_CHARACTERS = 180
MAX_ACTIVE_MEMORIES = 50
RECENT_PROJECT_WINDOW_DAYS = 14
RECENT_PROJECT_TTL_DAYS = 30
DISMISSED_SUGGESTION_TTL_DAYS = 14


class StructuredMemoryValidationError(ValueError):
    pass


class StructuredMemoryNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class StructuredMemoryResult:
    items: tuple[LifeOSMemory, ...]

    def to_dict(self) -> dict[str, Any]:
        counts: dict[str, int] = {kind: 0 for kind in sorted(MEMORY_TYPES)}
        for item in self.items:
            counts[item.memory_type] = counts.get(item.memory_type, 0) + 1
        return {
            "items": [memory_to_dict(item) for item in self.items],
            "counts": {"active": len(self.items), **counts},
            "policy": {
                "structured_only": True,
                "inspectable": True,
                "deletable": True,
                "stores_chat_transcripts": False,
                "stores_raw_document_text": False,
                "automatic_personal_inference": False,
            },
        }


def _clean_text(value: Any, *, field: str, limit: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        raise StructuredMemoryValidationError(f"{field} is required.")
    if len(text) > limit:
        raise StructuredMemoryValidationError(f"{field} is too long.")
    return text


def _safe_key(value: Any, *, fallback: str) -> str:
    raw = " ".join(str(value or fallback).split()).strip().casefold()
    key = re.sub(r"[^a-z0-9._:-]+", "-", raw).strip("-")
    return (key or fallback)[:160]


def _now(value: datetime | None = None) -> datetime:
    return value or datetime.utcnow()


def _active_query(*, owner_id: int, now: datetime | None = None):
    effective_now = _now(now)
    return LifeOSMemory.query.filter(
        LifeOSMemory.user_id == int(owner_id),
        LifeOSMemory.status == "active",
        or_(LifeOSMemory.expires_at.is_(None), LifeOSMemory.expires_at > effective_now),
    )


def memory_to_dict(item: LifeOSMemory) -> dict[str, Any]:
    return {
        "id": item.id,
        "type": item.memory_type,
        "key": item.memory_key,
        "label": item.label,
        "value": item.value,
        "scope": {
            "type": item.scope_type,
            "id": item.scope_id,
        } if item.scope_type else None,
        "source": {
            "type": item.source_type,
            "id": item.source_id,
            "user_confirmed": bool(item.user_confirmed),
        },
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "last_used_at": item.last_used_at.isoformat() if item.last_used_at else None,
        "expires_at": item.expires_at.isoformat() if item.expires_at else None,
        "status": item.status,
    }


def list_owned_memories(*, owner_id: int, memory_type: str | None = None, now: datetime | None = None) -> StructuredMemoryResult:
    query = _active_query(owner_id=owner_id, now=now)
    if memory_type:
        normalized = str(memory_type).strip()
        if normalized not in MEMORY_TYPES:
            raise StructuredMemoryValidationError("Unsupported LifeOS memory type.")
        query = query.filter(LifeOSMemory.memory_type == normalized)
    items = tuple(
        query.order_by(LifeOSMemory.updated_at.desc(), LifeOSMemory.id.desc())
        .limit(MAX_ACTIVE_MEMORIES)
        .all()
    )
    return StructuredMemoryResult(items=items)


def _upsert_memory(
    *,
    owner_id: int,
    memory_type: str,
    memory_key: str,
    label: str,
    value: dict[str, Any],
    scope_type: str | None = None,
    scope_id: int | None = None,
    source_type: str,
    source_id: int | None = None,
    user_confirmed: bool,
    expires_at: datetime | None = None,
    now: datetime | None = None,
) -> LifeOSMemory:
    if memory_type not in MEMORY_TYPES:
        raise StructuredMemoryValidationError("Unsupported LifeOS memory type.")
    effective_now = _now(now)
    item = LifeOSMemory.query.filter_by(
        user_id=int(owner_id), memory_type=memory_type, memory_key=memory_key
    ).first()
    if item is None:
        item = LifeOSMemory(
            user_id=int(owner_id),
            memory_type=memory_type,
            memory_key=memory_key,
            created_at=effective_now,
        )
        db.session.add(item)
    item.label = label[:MAX_MEMORY_LABEL_CHARACTERS]
    item.value_json = json.dumps(value, ensure_ascii=False, sort_keys=True)
    item.scope_type = scope_type
    item.scope_id = scope_id
    item.source_type = source_type
    item.source_id = source_id
    item.user_confirmed = bool(user_confirmed)
    item.status = "active"
    item.updated_at = effective_now
    item.expires_at = expires_at
    return item


def save_owned_user_memory(
    *,
    owner_id: int,
    memory_type: str,
    label: str,
    value: str,
    key: str | None = None,
    project_id: int | None = None,
) -> LifeOSMemory:
    """Save an explicit user-controlled preference or current focus.

    This endpoint intentionally does not accept arbitrary JSON or hidden source
    data.  The user provides a short visible value and can delete it later.
    """

    kind = str(memory_type or "").strip()
    if kind not in USER_WRITABLE_TYPES:
        raise StructuredMemoryValidationError("Only preferences and current focus can be saved directly.")
    clean_label = _clean_text(label, field="Memory label", limit=MAX_MEMORY_LABEL_CHARACTERS)
    clean_value = _clean_text(value, field="Memory value", limit=MAX_MEMORY_VALUE_CHARACTERS)

    scope_type = None
    scope_id = None
    if project_id not in (None, ""):
        project = Project.query.filter_by(id=int(project_id), user_id=int(owner_id)).first()
        if project is None:
            raise StructuredMemoryValidationError("Project not found.")
        scope_type = "project"
        scope_id = int(project.id)

    if kind == "current_focus":
        memory_key = "current"
        # One current focus means the previous one is replaced, not accumulated.
        label_text = clean_label or "Current focus"
    else:
        memory_key = _safe_key(key or clean_label, fallback="preference")
        label_text = clean_label

    item = _upsert_memory(
        owner_id=owner_id,
        memory_type=kind,
        memory_key=memory_key,
        label=label_text,
        value={"text": clean_value},
        scope_type=scope_type,
        scope_id=scope_id,
        source_type="user_confirmed",
        user_confirmed=True,
    )
    db.session.commit()
    return item


def delete_owned_memory(*, owner_id: int, memory_id: int) -> None:
    item = LifeOSMemory.query.filter_by(id=int(memory_id), user_id=int(owner_id)).first()
    if item is None:
        raise StructuredMemoryNotFoundError("Memory not found.")
    db.session.delete(item)
    db.session.commit()


def clear_owned_memories(*, owner_id: int) -> int:
    items = LifeOSMemory.query.filter_by(user_id=int(owner_id)).all()
    for item in items:
        db.session.delete(item)
    if items:
        db.session.commit()
    return len(items)


def refresh_owned_structured_memory(*, owner_id: int, now: datetime | None = None) -> StructuredMemoryResult:
    """Refresh only safe system-derived memory: recently active owned projects."""

    effective_now = _now(now)
    cutoff = effective_now - timedelta(days=RECENT_PROJECT_WINDOW_DAYS)
    projects = (
        Project.query.filter(
            Project.user_id == int(owner_id),
            Project.updated_at.isnot(None),
            Project.updated_at >= cutoff,
        )
        .order_by(Project.updated_at.desc(), Project.id.desc())
        .limit(5)
        .all()
    )

    # Recent activity can surface a project even when its project row itself was
    # not edited recently (for example a task was created inside it).
    activity_rows = (
        LifeOSActivityEvent.query.filter(
            LifeOSActivityEvent.user_id == int(owner_id),
            LifeOSActivityEvent.project_id.isnot(None),
            LifeOSActivityEvent.created_at >= cutoff,
        )
        .order_by(LifeOSActivityEvent.created_at.desc(), LifeOSActivityEvent.id.desc())
        .limit(30)
        .all()
    )
    seen = {int(project.id): project for project in projects}
    for row in activity_rows:
        pid = int(row.project_id or 0)
        if not pid or pid in seen:
            continue
        project = Project.query.filter_by(id=pid, user_id=int(owner_id)).first()
        if project is not None:
            seen[pid] = project
        if len(seen) >= 5:
            break

    active_keys: set[str] = set()
    for project in list(seen.values())[:5]:
        key = f"project:{project.id}"
        active_keys.add(key)
        last_at = project.updated_at or effective_now
        matching_activity = next((row for row in activity_rows if row.project_id == project.id), None)
        if matching_activity and matching_activity.created_at and matching_activity.created_at > last_at:
            last_at = matching_activity.created_at
        _upsert_memory(
            owner_id=owner_id,
            memory_type="recent_project",
            memory_key=key,
            label=project.title,
            value={"project_id": project.id, "project_title": project.title, "last_activity_at": last_at.isoformat()},
            scope_type="project",
            scope_id=project.id,
            source_type="workspace_activity",
            user_confirmed=False,
            expires_at=effective_now + timedelta(days=RECENT_PROJECT_TTL_DAYS),
            now=effective_now,
        )

    stale_recent = LifeOSMemory.query.filter_by(user_id=int(owner_id), memory_type="recent_project", status="active").all()
    for item in stale_recent:
        if item.memory_key not in active_keys:
            item.status = "expired"
            item.updated_at = effective_now

    db.session.commit()
    return list_owned_memories(owner_id=owner_id, now=effective_now)


def remember_dismissed_suggestion(*, owner_id: int, notification, now: datetime | None = None) -> LifeOSMemory | None:
    """Record a visible, expiring dismissal without storing notification prose as hidden history."""

    event = getattr(notification, "event", None)
    if event is None:
        return None
    effective_now = _now(now)
    key = f"{event.event_type}:{event.object_type}:{event.object_id or 0}"
    item = _upsert_memory(
        owner_id=owner_id,
        memory_type="dismissed_suggestion",
        memory_key=key,
        label=f"Dismissed {event.event_type}",
        value={
            "event_type": event.event_type,
            "object_type": event.object_type,
            "object_id": event.object_id,
            "project_id": event.project_id,
        },
        scope_type=event.object_type if event.object_id else None,
        scope_id=event.object_id,
        source_type="notification_dismissal",
        source_id=getattr(notification, "id", None),
        user_confirmed=True,
        expires_at=effective_now + timedelta(days=DISMISSED_SUGGESTION_TTL_DAYS),
        now=effective_now,
    )
    return item


def has_active_dismissed_suggestion(*, owner_id: int, event, now: datetime | None = None) -> bool:
    key = f"{event.event_type}:{event.object_type}:{event.object_id or 0}"
    return _active_query(owner_id=owner_id, now=now).filter_by(
        memory_type="dismissed_suggestion", memory_key=key
    ).first() is not None


def memory_context_rows(*, owner_id: int, project_id: int | None = None, now: datetime | None = None) -> list[dict[str, Any]]:
    """Return a bounded subset safe to expose as verified context facts."""

    items = list_owned_memories(owner_id=owner_id, now=now).items
    rows: list[dict[str, Any]] = []
    for item in items:
        if item.memory_type not in {"preference", "current_focus"}:
            continue
        if item.scope_type == "project" and project_id is not None and item.scope_id != int(project_id):
            continue
        if item.scope_type == "project" and project_id is None:
            continue
        text = str(item.value.get("text") or "").strip()
        if not text:
            continue
        rows.append({
            "key": f"memory.{item.memory_type}.{item.memory_key}",
            "value": text,
            "label": item.label,
            "memory_id": item.id,
            "fact_type": "user_confirmed" if item.user_confirmed else "derived",
        })
        if len(rows) >= 8:
            break
    return rows


def build_owned_memory_summary(*, owner_id: int, query: str = "", now: datetime | None = None) -> dict[str, Any]:
    result = refresh_owned_structured_memory(owner_id=owner_id, now=now)
    visible = [memory_to_dict(item) for item in result.items]
    user_items = [item for item in visible if item["type"] in {"preference", "current_focus"}]
    recent = [item for item in visible if item["type"] == "recent_project"]
    dismissed = [item for item in visible if item["type"] == "dismissed_suggestion"]
    normalized_query = " ".join(str(query or "").casefold().split())
    preference_items = [item for item in user_items if item["type"] == "preference"]
    focus_items = [item for item in user_items if item["type"] == "current_focus"]

    if not visible:
        summary = "I do not currently have any structured LifeOS memory saved for you."
    elif normalized_query and any(word in normalized_query for word in ("focus", "focusing")) and focus_items:
        value = str(focus_items[0].get("value", {}).get("text") or "").strip()
        summary = f"Your saved current focus is: {value}" if value else "You have a saved current focus in structured LifeOS memory."
    elif normalized_query and any(word in normalized_query for word in ("prefer", "preference", "review style", "answer style")) and preference_items:
        query_tokens = {token for token in normalized_query.replace("?", "").split() if len(token) > 2}
        def preference_score(item):
            haystack = f"{item.get('label', '')} {item.get('value', {}).get('text', '')}".casefold()
            return sum(1 for token in query_tokens if token in haystack)
        selected = max(preference_items, key=preference_score)
        value = str(selected.get("value", {}).get("text") or "").strip()
        summary = f"Your saved preference is: {value}" if value else "You have a saved preference in structured LifeOS memory."
    else:
        parts = []
        if user_items:
            parts.append(f"{len(user_items)} user-controlled memory item{'s' if len(user_items) != 1 else ''}")
        if recent:
            parts.append(f"{len(recent)} recently active project{'s' if len(recent) != 1 else ''}")
        if dismissed:
            parts.append(f"{len(dismissed)} active dismissed suggestion{'s' if len(dismissed) != 1 else ''}")
        summary = "Your structured LifeOS memory currently contains " + ", ".join(parts) + ". You can inspect or delete every item from Memory."
    return {
        "summary": summary,
        "items": visible,
        "counts": result.to_dict()["counts"],
        "policy": result.to_dict()["policy"],
        "verified_from_state": True,
        "user_controlled": True,
    }

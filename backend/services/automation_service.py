"""I17 — constrained LifeOS automation definitions, previews, and action building.

I17 automates verified intelligence work, not arbitrary code and not direct
workspace mutation. Schedules/event rules may run in the background through the
reviewed worker, but Project/Task/Note/Document writes still stay behind I9.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import true
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from database import db
from models import LifeOSAutomation, LifeOSAutomationRun, LifeOSIntelligenceEvent, Project
from services.automation_intelligence_service import (
    build_event_context_review_output,
    build_risk_escalation_output,
    build_today_briefing_output,
    build_unhandled_followup_output,
    build_weekly_review_output,
)


TRIGGER_TYPES = {
    "schedule_daily": {
        "label": "Every day",
        "description": "Run once each day at a selected local time.",
        "fields": ["hour", "minute"],
    },
    "schedule_weekly": {
        "label": "Every week",
        "description": "Run once each week on a selected weekday and time.",
        "fields": ["weekday", "hour", "minute"],
    },
    "event": {
        "label": "When something changes",
        "description": "Run when an allow-listed I14 event becomes relevant.",
        "fields": ["event_type"],
    },
}

EVENT_TYPES = {
    "task.overdue",
    "task.blocked",
    "deadline.approaching",
    "project.overdue",
    "project.deadline_approaching",
    "document.intelligence_stale",
    "document.version_changed",
}

ACTION_TYPES = {
    "today_briefing": {
        "label": "Morning intelligence briefing",
        "description": "Combine priorities, deadlines, document attention, study state, and recent changes into Today's verified briefing.",
        "scope": "workspace",
    },
    "portfolio_review": {
        "label": "Weekly intelligence review",
        "description": "Review all projects plus this week's meaningful activity and rank what deserves attention next.",
        "scope": "workspace",
    },
    "project_review": {
        "label": "Review one project",
        "description": "Run the constrained I8 project review agent for one owned project.",
        "scope": "project",
    },
    "risk_escalation": {
        "label": "Detect compound project risk",
        "description": "Escalate only when several trusted signals combine into a broader project risk; do not repeat basic due-task reminders.",
        "scope": "workspace",
    },
    "unhandled_followup": {
        "label": "Find unhandled document follow-ups",
        "description": "Find current document risks/actions that still have no confirmed task or note provenance.",
        "scope": "workspace",
    },
    "attention_notice": {
        "label": "Review a triggering event in context",
        "description": "Enrich a selected I14 event with relevant project priorities before notifying you.",
        "scope": "event",
    },
}

MAX_AUTOMATIONS_PER_USER = 50
MAX_RUN_HISTORY = 100

VISUAL_FLOW_VERSION = 1
VISUAL_NODE_IDS = ("trigger", "intelligence", "delivery")
VISUAL_NODE_KINDS = {
    "trigger": "trigger",
    "intelligence": "intelligence",
    "delivery": "delivery",
}
VISUAL_DEFAULT_POSITIONS = {
    "trigger": {"x": 90.0, "y": 150.0},
    "intelligence": {"x": 390.0, "y": 150.0},
    "delivery": {"x": 690.0, "y": 150.0},
}
VISUAL_EDGES = (
    {"id": "trigger-intelligence", "source": "trigger", "target": "intelligence"},
    {"id": "intelligence-delivery", "source": "intelligence", "target": "delivery"},
)


class AutomationValidationError(ValueError):
    pass


class AutomationNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class AutomationPreviewResult:
    automation: LifeOSAutomation
    run: LifeOSAutomationRun
    output: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "automation": automation_to_dict(self.automation),
            "run": automation_run_to_dict(self.run),
            "output": self.output,
            "verified_from_state": True,
            "workspace_mutation": False,
            "execution_mode": "preview",
        }


def _finite_position(value: Any, *, fallback: dict[str, float]) -> dict[str, float]:
    raw = value if isinstance(value, dict) else {}
    result: dict[str, float] = {}
    for key in ("x", "y"):
        candidate = raw.get(key, fallback[key])
        try:
            parsed = float(candidate)
        except (TypeError, ValueError) as error:
            raise AutomationValidationError("Visual flow node positions must be numeric.") from error
        if parsed != parsed or parsed in (float("inf"), float("-inf")) or abs(parsed) > 5000:
            raise AutomationValidationError("Visual flow node position is outside the supported canvas.")
        result[key] = round(parsed, 2)
    return result


def default_visual_graph(*, trigger_type: str, action_type: str) -> dict[str, Any]:
    return {
        "version": VISUAL_FLOW_VERSION,
        "nodes": [
            {
                "id": node_id,
                "kind": VISUAL_NODE_KINDS[node_id],
                "position": dict(VISUAL_DEFAULT_POSITIONS[node_id]),
                "semantic_type": (
                    trigger_type if node_id == "trigger"
                    else action_type if node_id == "intelligence"
                    else "in_app_notification"
                ),
            }
            for node_id in VISUAL_NODE_IDS
        ],
        "edges": [dict(edge) for edge in VISUAL_EDGES],
        "safety": {
            "workspace_mutation": False,
            "delivery": "in_app",
            "future_workspace_actions_require": "I9_confirmation",
        },
    }


def validate_visual_graph(
    raw: Any,
    *,
    trigger_type: str,
    action_type: str,
) -> dict[str, Any]:
    """Validate I18 layout metadata without allowing the canvas to redefine execution.

    The I17 trigger/action columns remain authoritative. I18 persists only the
    reviewed three-node presentation and node positions. Extra nodes/edges,
    executable code, URLs, or alternate delivery channels are rejected.
    """

    if raw in (None, {}, ""):
        return default_visual_graph(trigger_type=trigger_type, action_type=action_type)
    if not isinstance(raw, dict):
        raise AutomationValidationError("Visual flow must be an object.")
    try:
        version = int(raw.get("version", VISUAL_FLOW_VERSION))
    except (TypeError, ValueError) as error:
        raise AutomationValidationError("Unsupported visual flow version.") from error
    if version != VISUAL_FLOW_VERSION:
        raise AutomationValidationError("Unsupported visual flow version.")

    raw_nodes = raw.get("nodes")
    if not isinstance(raw_nodes, list) or len(raw_nodes) != len(VISUAL_NODE_IDS):
        raise AutomationValidationError("Visual flow must contain Trigger, Intelligence, and Notification nodes.")
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for node in raw_nodes:
        if not isinstance(node, dict):
            raise AutomationValidationError("Invalid visual flow node.")
        node_id = str(node.get("id") or "").strip()
        if node_id not in VISUAL_NODE_IDS or node_id in nodes_by_id:
            raise AutomationValidationError("Visual flow contains an unsupported node.")
        kind = str(node.get("kind") or VISUAL_NODE_KINDS[node_id]).strip()
        if kind != VISUAL_NODE_KINDS[node_id]:
            raise AutomationValidationError("Visual flow node type does not match the reviewed automation contract.")
        nodes_by_id[node_id] = {
            "id": node_id,
            "kind": kind,
            "position": _finite_position(node.get("position"), fallback=VISUAL_DEFAULT_POSITIONS[node_id]),
        }
    if set(nodes_by_id) != set(VISUAL_NODE_IDS):
        raise AutomationValidationError("Visual flow is missing a required node.")

    raw_edges = raw.get("edges")
    if raw_edges is not None:
        if not isinstance(raw_edges, list) or len(raw_edges) != len(VISUAL_EDGES):
            raise AutomationValidationError("Visual flow connections are fixed in Automations V1.")
        actual = {(str(edge.get("source")), str(edge.get("target"))) for edge in raw_edges if isinstance(edge, dict)}
        expected = {(edge["source"], edge["target"]) for edge in VISUAL_EDGES}
        if actual != expected:
            raise AutomationValidationError("Visual flow connections are fixed in Automations V1.")

    canonical = default_visual_graph(trigger_type=trigger_type, action_type=action_type)
    canonical["nodes"] = [
        {
            **next(item for item in canonical["nodes"] if item["id"] == node_id),
            "position": nodes_by_id[node_id]["position"],
        }
        for node_id in VISUAL_NODE_IDS
    ]
    return canonical


def automation_visual_graph(item: LifeOSAutomation) -> dict[str, Any]:
    try:
        return validate_visual_graph(
            item.visual_graph,
            trigger_type=item.trigger_type,
            action_type=item.action_type,
        )
    except AutomationValidationError:
        return default_visual_graph(trigger_type=item.trigger_type, action_type=item.action_type)


def automation_registry() -> dict[str, Any]:
    return {
        "triggers": [
            {"type": key, **value}
            for key, value in TRIGGER_TYPES.items()
        ],
        "event_types": sorted(EVENT_TYPES),
        "actions": [
            {"type": key, **value}
            for key, value in ACTION_TYPES.items()
        ],
        "templates": [
            {
                "key": "morning_briefing",
                "name": "Morning intelligence briefing",
                "description": "Every morning, decide what actually deserves your attention across projects, deadlines, documents, study, and recent changes.",
                "trigger_type": "schedule_daily",
                "trigger_config": {"hour": 8, "minute": 0},
                "action_type": "today_briefing",
                "action_config": {},
            },
            {
                "key": "weekly_review",
                "name": "Weekly intelligence review",
                "description": "Once a week, combine project priorities with what changed and surface the strongest next focus.",
                "trigger_type": "schedule_weekly",
                "trigger_config": {"weekday": 6, "hour": 18, "minute": 0},
                "action_type": "portfolio_review",
                "action_config": {},
            },
            {
                "key": "risk_escalation",
                "name": "Project risk escalation",
                "description": "Check daily for compound risk patterns instead of sending another simple deadline reminder.",
                "trigger_type": "schedule_daily",
                "trigger_config": {"hour": 17, "minute": 30},
                "action_type": "risk_escalation",
                "action_config": {},
            },
            {
                "key": "unhandled_followup",
                "name": "Unhandled document follow-up",
                "description": "Check whether current document risks/actions still lack a confirmed task or note follow-up.",
                "trigger_type": "schedule_daily",
                "trigger_config": {"hour": 18, "minute": 0},
                "action_type": "unhandled_followup",
                "action_config": {},
            },
        ],
        "limits": {"max_automations_per_user": MAX_AUTOMATIONS_PER_USER},
        "visual_flow": {
            "version": VISUAL_FLOW_VERSION,
            "node_order": list(VISUAL_NODE_IDS),
            "delivery_type": "in_app_notification",
            "connections_fixed": True,
            "layout_persisted": True,
            "execution_source": "I17_allowlisted_trigger_and_action",
        },
        "safety": {
            "arbitrary_code": False,
            "arbitrary_sql": False,
            "arbitrary_urls": False,
            "workspace_mutation": False,
            "i9_confirmation_required_for_future_mutations": True,
            "background_execution_available": True,
            "single_worker_v1": True,
        },
    }


def _clean_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name:
        raise AutomationValidationError("Automation name is required.")
    if len(name) > 160:
        raise AutomationValidationError("Automation name is too long.")
    return name


def _timezone(name: Any) -> ZoneInfo:
    zone_name = str(name or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(zone_name)
    except ZoneInfoNotFoundError as error:
        raise AutomationValidationError("Use a valid IANA timezone, for example Africa/Cairo or UTC.") from error


def _int_between(value: Any, minimum: int, maximum: int, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise AutomationValidationError(f"{label} must be a number.") from error
    if parsed < minimum or parsed > maximum:
        raise AutomationValidationError(f"{label} must be between {minimum} and {maximum}.")
    return parsed


def validate_trigger(trigger_type: Any, raw: Any) -> tuple[str, dict[str, Any]]:
    kind = str(trigger_type or "").strip()
    if kind not in TRIGGER_TYPES:
        raise AutomationValidationError("Unsupported automation trigger.")
    config = raw if isinstance(raw, dict) else {}

    if kind == "schedule_daily":
        return kind, {
            "hour": _int_between(config.get("hour", 8), 0, 23, "Hour"),
            "minute": _int_between(config.get("minute", 0), 0, 59, "Minute"),
        }
    if kind == "schedule_weekly":
        return kind, {
            "weekday": _int_between(config.get("weekday", 0), 0, 6, "Weekday"),
            "hour": _int_between(config.get("hour", 8), 0, 23, "Hour"),
            "minute": _int_between(config.get("minute", 0), 0, 59, "Minute"),
        }

    event_type = str(config.get("event_type") or "").strip()
    if event_type not in EVENT_TYPES:
        raise AutomationValidationError("Unsupported LifeOS event trigger.")
    return kind, {"event_type": event_type}


def validate_action(*, owner_id: int, action_type: Any, raw: Any) -> tuple[str, dict[str, Any]]:
    kind = str(action_type or "").strip()
    if kind not in ACTION_TYPES:
        raise AutomationValidationError("Unsupported automation action.")
    config = raw if isinstance(raw, dict) else {}

    if kind == "project_review":
        project_id = _int_between(config.get("project_id"), 1, 2_147_483_647, "Project")
        project = Project.query.filter_by(id=project_id, user_id=owner_id).first()
        if project is None:
            raise AutomationValidationError("Selected project was not found.")
        return kind, {"project_id": project_id}

    # The other V1 actions accept no arbitrary payload.
    return kind, {}


def calculate_next_run_at(
    *,
    trigger_type: str,
    trigger_config: dict[str, Any],
    timezone_name: str,
    now: datetime | None = None,
) -> datetime | None:
    if trigger_type == "event":
        return None

    zone = _timezone(timezone_name)
    if now is None:
        current_utc = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        current_utc = now.replace(tzinfo=timezone.utc)
    else:
        current_utc = now.astimezone(timezone.utc)
    local_now = current_utc.astimezone(zone)

    hour = int(trigger_config["hour"])
    minute = int(trigger_config["minute"])
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if trigger_type == "schedule_daily":
        if candidate <= local_now:
            candidate += timedelta(days=1)
    elif trigger_type == "schedule_weekly":
        target_weekday = int(trigger_config["weekday"])
        days = (target_weekday - local_now.weekday()) % 7
        candidate += timedelta(days=days)
        if candidate <= local_now:
            candidate += timedelta(days=7)
    else:
        raise AutomationValidationError("Unsupported schedule trigger.")

    # Persist schedule timestamps in naive UTC, matching existing LifeOS timestamp conventions.
    return candidate.astimezone(timezone.utc).replace(tzinfo=None)


def event_matches_automation(automation: LifeOSAutomation, event: LifeOSIntelligenceEvent) -> bool:
    if automation.trigger_type != "event" or not automation.enabled:
        return False
    if event.user_id != automation.user_id:
        return False
    return automation.trigger_config.get("event_type") == event.event_type


def _owned_automation(*, owner_id: int, automation_id: int) -> LifeOSAutomation:
    automation = LifeOSAutomation.query.filter_by(id=automation_id, user_id=owner_id).first()
    if automation is None:
        raise AutomationNotFoundError("Automation not found.")
    return automation


def automation_to_dict(item: LifeOSAutomation) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "enabled": bool(item.enabled),
        "status": item.status,
        "trigger": {"type": item.trigger_type, "config": item.trigger_config},
        "action": {"type": item.action_type, "config": item.action_config},
        "visual_graph": automation_visual_graph(item),
        "timezone": item.timezone,
        "next_run_at": item.next_run_at.isoformat() if item.next_run_at else None,
        "last_run_at": item.last_run_at.isoformat() if item.last_run_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "safety": {"workspace_mutation": False, "confirmation_boundary": "I9"},
    }


def automation_run_to_dict(item: LifeOSAutomationRun) -> dict[str, Any]:
    return {
        "id": item.id,
        "automation_id": item.automation_id,
        "status": item.status,
        "trigger_source": item.trigger_source,
        "event_id": item.event_id,
        "dry_run": bool(item.dry_run),
        "output": item.output,
        "error_message": item.error_message,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "finished_at": item.finished_at.isoformat() if item.finished_at else None,
    }


def list_owned_automations(*, owner_id: int) -> tuple[LifeOSAutomation, ...]:
    return tuple(
        LifeOSAutomation.query.filter_by(user_id=owner_id)
        .order_by(LifeOSAutomation.created_at.desc(), LifeOSAutomation.id.desc())
        .all()
    )


def create_owned_automation(
    *,
    owner_id: int,
    name: Any,
    description: Any = None,
    enabled: bool = False,
    trigger_type: Any,
    trigger_config: Any,
    action_type: Any,
    action_config: Any,
    timezone_name: Any = "UTC",
    visual_graph: Any = None,
) -> LifeOSAutomation:
    if LifeOSAutomation.query.filter_by(user_id=owner_id).count() >= MAX_AUTOMATIONS_PER_USER:
        raise AutomationValidationError("Automation limit reached.")
    clean_name = _clean_name(name)
    if LifeOSAutomation.query.filter_by(user_id=owner_id, name=clean_name).first() is not None:
        raise AutomationValidationError("An automation with that name already exists.")

    trigger_kind, trigger = validate_trigger(trigger_type, trigger_config)
    action_kind, action = validate_action(owner_id=owner_id, action_type=action_type, raw=action_config)
    graph = validate_visual_graph(visual_graph, trigger_type=trigger_kind, action_type=action_kind)
    zone = _timezone(timezone_name)
    zone_name = zone.key
    now = datetime.utcnow()
    next_run_at = calculate_next_run_at(
        trigger_type=trigger_kind,
        trigger_config=trigger,
        timezone_name=zone_name,
        now=now,
    )

    item = LifeOSAutomation(
        user_id=owner_id,
        name=clean_name,
        description=str(description or "").strip() or None,
        enabled=bool(enabled),
        trigger_type=trigger_kind,
        trigger_config_json=json.dumps(trigger, ensure_ascii=False, sort_keys=True),
        action_type=action_kind,
        action_config_json=json.dumps(action, ensure_ascii=False, sort_keys=True),
        visual_graph_json=json.dumps(graph, ensure_ascii=False, sort_keys=True),
        timezone=zone_name,
        status="ready",
        next_run_at=next_run_at,
        created_at=now,
        updated_at=now,
    )
    db.session.add(item)
    db.session.commit()
    return item


def update_owned_automation(*, owner_id: int, automation_id: int, payload: dict[str, Any]) -> LifeOSAutomation:
    item = _owned_automation(owner_id=owner_id, automation_id=automation_id)

    if "name" in payload:
        clean_name = _clean_name(payload.get("name"))
        duplicate = LifeOSAutomation.query.filter(
            LifeOSAutomation.user_id == owner_id,
            LifeOSAutomation.name == clean_name,
            LifeOSAutomation.id != item.id,
        ).first()
        if duplicate is not None:
            raise AutomationValidationError("An automation with that name already exists.")
        item.name = clean_name
    if "description" in payload:
        item.description = str(payload.get("description") or "").strip() or None

    trigger_kind, trigger = validate_trigger(
        payload.get("trigger_type", item.trigger_type),
        payload.get("trigger_config", item.trigger_config),
    )
    action_kind, action = validate_action(
        owner_id=owner_id,
        action_type=payload.get("action_type", item.action_type),
        raw=payload.get("action_config", item.action_config),
    )
    graph = validate_visual_graph(
        payload.get("visual_graph", item.visual_graph),
        trigger_type=trigger_kind,
        action_type=action_kind,
    )
    zone = _timezone(payload.get("timezone", item.timezone))

    item.trigger_type = trigger_kind
    item.trigger_config_json = json.dumps(trigger, ensure_ascii=False, sort_keys=True)
    item.action_type = action_kind
    item.action_config_json = json.dumps(action, ensure_ascii=False, sort_keys=True)
    item.visual_graph_json = json.dumps(graph, ensure_ascii=False, sort_keys=True)
    item.timezone = zone.key
    if "enabled" in payload:
        item.enabled = bool(payload.get("enabled"))
    item.next_run_at = calculate_next_run_at(
        trigger_type=item.trigger_type,
        trigger_config=item.trigger_config,
        timezone_name=item.timezone,
        now=datetime.utcnow(),
    )
    item.updated_at = datetime.utcnow()
    db.session.commit()
    return item


def delete_owned_automation(*, owner_id: int, automation_id: int) -> None:
    item = _owned_automation(owner_id=owner_id, automation_id=automation_id)
    db.session.delete(item)
    db.session.commit()


def list_owned_automation_runs(*, owner_id: int, automation_id: int, limit: int = 20) -> tuple[LifeOSAutomationRun, ...]:
    _owned_automation(owner_id=owner_id, automation_id=automation_id)
    bounded = max(1, min(int(limit or 20), MAX_RUN_HISTORY))
    return tuple(
        LifeOSAutomationRun.query.filter_by(user_id=owner_id, automation_id=automation_id)
        .order_by(LifeOSAutomationRun.started_at.desc(), LifeOSAutomationRun.id.desc())
        .limit(bounded)
        .all()
    )


def build_owned_automation_output(
    *,
    owner_id: int,
    automation: LifeOSAutomation,
    event_id: int | None = None,
) -> dict[str, Any]:
    """Run one reviewed, read-only intelligence action.

    The result may ask I17 to create a *notification metadata event*, but this
    function itself never mutates user workspace resources.
    """

    if automation.action_type == "today_briefing":
        return build_today_briefing_output(owner_id=owner_id)
    if automation.action_type == "portfolio_review":
        return build_weekly_review_output(owner_id=owner_id)
    if automation.action_type == "project_review":
        project_id = int(automation.action_config["project_id"])
        from services.project_review_agent_service import run_owned_project_review_agent
        result = run_owned_project_review_agent(project_id=project_id, owner_id=owner_id).to_dict(include_diagnostics=False)
        priorities = result.get("priorities", [])
        title = f"Project review ready: {result.get('project_title') or 'Project'}"
        summary = f"Reviewed {result.get('project_title') or 'the project'} and found {len(priorities)} ranked priorit{'y' if len(priorities) == 1 else 'ies'}."
        if priorities:
            summary += f" Top focus: {priorities[0].get('title')}."
        return {
            "kind": "project_review",
            "project_id": project_id,
            "title": title,
            "summary": summary,
            "attention_level": result.get("attention_level"),
            "priorities": priorities[:5],
            "priority_count": len(priorities),
            "verified_from_state": True,
            "read_only": True,
            "notification": {
                "should_notify": True,
                "event_type": "automation.project_review_ready",
                "severity": "high" if result.get("attention_level") == "high" else "medium" if result.get("attention_level") == "medium" else "info",
                "title": title,
                "message": summary,
                "dedupe_scope": "run",
                "action_label": "Open project",
                "action_href": f"/projects/{project_id}",
                "ask_query": f"Review my project #{project_id} and tell me what needs attention",
            },
        }
    if automation.action_type == "risk_escalation":
        return build_risk_escalation_output(owner_id=owner_id)
    if automation.action_type == "unhandled_followup":
        return build_unhandled_followup_output(owner_id=owner_id)
    if automation.action_type == "attention_notice":
        if event_id is None:
            return {
                "kind": "event_context_review",
                "title": "Event context review is ready",
                "summary": "This event automation is ready. A real event-triggered run will review the verified I14 event in project context.",
                "verified_from_state": True,
                "read_only": True,
                "notification": {"should_notify": False},
            }
        event = LifeOSIntelligenceEvent.query.filter_by(id=event_id, user_id=owner_id).first()
        if event is None:
            raise AutomationValidationError("Trigger event was not found.")
        if not event_matches_automation(automation, event):
            raise AutomationValidationError("The event does not match this automation trigger.")
        return build_event_context_review_output(owner_id=owner_id, event=event)
    raise AutomationValidationError("Unsupported automation action.")


def _preview_output(*, owner_id: int, automation: LifeOSAutomation, event_id: int | None = None) -> dict[str, Any]:
    return build_owned_automation_output(owner_id=owner_id, automation=automation, event_id=event_id)


def preview_owned_automation(
    *,
    owner_id: int,
    automation_id: int,
    event_id: int | None = None,
) -> AutomationPreviewResult:
    automation = _owned_automation(owner_id=owner_id, automation_id=automation_id)
    now = datetime.utcnow()
    run = LifeOSAutomationRun(
        automation_id=automation.id,
        user_id=owner_id,
        status="running",
        trigger_source="preview",
        event_id=event_id,
        dry_run=True,
        started_at=now,
    )
    db.session.add(run)
    db.session.flush()
    try:
        output = _preview_output(owner_id=owner_id, automation=automation, event_id=event_id)
        run.status = "succeeded"
        run.output_json = json.dumps(output, ensure_ascii=False, sort_keys=True, default=str)
        run.finished_at = datetime.utcnow()
        db.session.commit()
    except Exception as error:
        run.status = "failed"
        run.error_message = str(error)[:2000]
        run.finished_at = datetime.utcnow()
        db.session.commit()
        raise
    return AutomationPreviewResult(automation=automation, run=run, output=output)


def due_owned_schedule_automations(*, owner_id: int, now: datetime | None = None) -> tuple[LifeOSAutomation, ...]:
    effective_now = now or datetime.utcnow()
    return tuple(
        LifeOSAutomation.query.filter(
            LifeOSAutomation.user_id == owner_id,
            LifeOSAutomation.enabled == true(),
            LifeOSAutomation.trigger_type.in_(("schedule_daily", "schedule_weekly")),
            LifeOSAutomation.next_run_at.isnot(None),
            LifeOSAutomation.next_run_at <= effective_now,
        ).order_by(LifeOSAutomation.next_run_at.asc()).all()
    )

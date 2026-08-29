"""I17 read-only intelligence actions used by real automations.

These actions deliberately *analyze and prepare*; they never create/update/delete
Project, Task, Note, Document, Module, or Collection rows.  The only writes that
I17 performs are automation audit rows plus I14/I15 delivery metadata.

The goal is to automate the useful reasoning LifeOS already knows how to do,
not duplicate the existing basic due-task email/reminder system.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from models import LifeOSContextLink, LifeOSIntelligenceEvent
from services.home_intelligence_service import build_owned_home_intelligence
from services.lifeos_activity_service import build_owned_recent_activity
from services.project_review_agent_service import (
    AgentPriority,
    run_owned_portfolio_review_agent,
    run_owned_project_review_agent,
)


MAX_AUTOMATION_PRIORITIES = 5
MAX_ESCALATED_PROJECTS = 3
MAX_UNHANDLED_FINDINGS = 5


def _severity_from_attention(value: Any) -> str:
    text = str(value or "normal").strip().casefold()
    if text in {"critical", "high"}:
        return "high"
    if text == "medium":
        return "medium"
    if text == "low":
        return "normal"
    return "info"


def _fingerprint(parts: list[str]) -> str:
    normalized = "\n".join(" ".join(str(part or "").split()) for part in parts)
    return sha256(normalized.encode("utf-8")).hexdigest()[:20]


def _priority_payload(item: AgentPriority) -> dict[str, Any]:
    return item.to_dict(include_diagnostics=False)


def build_today_briefing_output(*, owner_id: int) -> dict[str, Any]:
    home = build_owned_home_intelligence(owner_id=owner_id).to_dict()
    briefing = home.get("briefing") or {}
    focus = home.get("focus") or {}
    priorities = list(focus.get("priorities") or [])[:MAX_AUTOMATION_PRIORITIES]
    top_focus = priorities[0].get("title") if priorities else None
    summary = str(briefing.get("summary") or "LifeOS prepared today's verified workspace review.")
    if top_focus:
        summary = f"{summary} Top focus: {top_focus}."
    return {
        "kind": "today_briefing",
        "title": str(briefing.get("headline") or "Your LifeOS morning briefing is ready"),
        "summary": summary,
        "attention_level": briefing.get("attention_level") or focus.get("attention_level") or "normal",
        "signals": briefing.get("signals") or [],
        "priorities": priorities,
        "priority_count": int((focus.get("counts") or {}).get("total", len(priorities)) or len(priorities)),
        "verified_from_state": True,
        "read_only": True,
        "notification": {
            "should_notify": True,
            "event_type": "automation.today_briefing_ready",
            "severity": _severity_from_attention(briefing.get("attention_level")),
            "title": str(briefing.get("headline") or "Your LifeOS morning briefing is ready"),
            "message": summary,
            "dedupe_scope": "run",
            "action_label": "Open Today",
            "action_href": "/dashboard",
            "ask_query": "What should I focus on today?",
        },
    }


def build_weekly_review_output(*, owner_id: int) -> dict[str, Any]:
    review = run_owned_portfolio_review_agent(owner_id=owner_id)
    activity = build_owned_recent_activity(
        owner_id=owner_id,
        query="What changed this week?",
        limit=20,
    )
    priorities = list(review.priorities)[:MAX_AUTOMATION_PRIORITIES]
    top = priorities[0] if priorities else None
    summary_parts = [
        f"Reviewed {review.reviewed_projects} of {review.total_owned_projects} project"
        f"{'s' if review.total_owned_projects != 1 else ''}",
        f"{activity.total_items} meaningful change{'s' if activity.total_items != 1 else ''} recorded this week",
    ]
    if top:
        summary_parts.append(f"top focus is {top.project_title} — {top.title}")
    else:
        summary_parts.append("no ranked blocker, near deadline, stale intelligence, or document risk currently outranks normal work")
    summary = ". ".join(part[:1].upper() + part[1:] for part in summary_parts) + "."
    title = "Your weekly LifeOS review is ready"
    return {
        "kind": "weekly_intelligence_review",
        "title": title,
        "summary": summary,
        "attention_level": review.attention_level,
        "reviewed_projects": review.reviewed_projects,
        "total_projects": review.total_owned_projects,
        "activity_count": activity.total_items,
        "activity_window": activity.window_label,
        "priorities": [_priority_payload(item) for item in priorities],
        "priority_count": len(review.priorities),
        "context_limited": bool(review.context_limited or activity.context_limited),
        "verified_from_state": True,
        "read_only": True,
        "notification": {
            "should_notify": True,
            "event_type": "automation.weekly_review_ready",
            "severity": _severity_from_attention(review.attention_level),
            "title": title,
            "message": summary,
            "dedupe_scope": "run",
            "action_label": "Open Ask LifeOS",
            "action_href": "/ask",
            "ask_query": "Review all my projects and tell me what needs attention this week.",
        },
    }


def build_risk_escalation_output(*, owner_id: int) -> dict[str, Any]:
    """Detect compound project risk rather than repeating one due-task reminder.

    A project is escalated only when trusted priorities form a broader pattern:
    * at least one high priority plus a second independent category; or
    * at least three medium-or-higher priorities across at least two categories.
    """

    review = run_owned_portfolio_review_agent(owner_id=owner_id)
    by_project: dict[int, list[AgentPriority]] = defaultdict(list)
    for priority in review.priorities:
        by_project[int(priority.project_id)].append(priority)

    escalations: list[dict[str, Any]] = []
    for project_id, priorities in by_project.items():
        categories = {item.category for item in priorities if item.severity in {"high", "medium"}}
        high = [item for item in priorities if item.severity == "high"]
        significant = [item for item in priorities if item.severity in {"high", "medium"}]
        should_escalate = (bool(high) and len(categories) >= 2) or (len(significant) >= 3 and len(categories) >= 2)
        if not should_escalate:
            continue
        ordered = significant[:3]
        project_title = priorities[0].project_title if priorities else f"Project {project_id}"
        severity = "high" if high else "medium"
        escalations.append({
            "project_id": project_id,
            "project_title": project_title,
            "severity": severity,
            "signal_count": len(significant),
            "categories": sorted(categories),
            "reasons": [
                {"title": item.title, "reason": item.reason, "category": item.category, "severity": item.severity}
                for item in ordered
            ],
            "recommended_action": "Review the combined signals as one project risk before lower-priority work.",
        })

    escalations.sort(key=lambda item: (0 if item["severity"] == "high" else 1, -int(item["signal_count"]), str(item["project_title"]).casefold()))
    escalations = escalations[:MAX_ESCALATED_PROJECTS]
    if escalations:
        lead = escalations[0]
        title = f"LifeOS found {len(escalations)} project risk pattern{'s' if len(escalations) != 1 else ''}"
        summary = (
            f"{lead['project_title']} has {lead['signal_count']} current signals across "
            f"{len(lead['categories'])} categories. LifeOS combined them instead of sending another simple deadline reminder."
        )
        fingerprint = _fingerprint([
            f"{item['project_id']}:{item['severity']}:{','.join(item['categories'])}:{item['signal_count']}"
            for item in escalations
        ])
        attention = "high" if any(item["severity"] == "high" for item in escalations) else "medium"
    else:
        title = "No compound project risk detected"
        summary = "LifeOS did not find a multi-signal project risk that needs escalation beyond existing reminders."
        fingerprint = "clear"
        attention = "normal"

    return {
        "kind": "risk_escalation",
        "title": title,
        "summary": summary,
        "attention_level": attention,
        "escalations": escalations,
        "verified_from_state": True,
        "read_only": True,
        "notification": {
            "should_notify": bool(escalations),
            "event_type": "automation.project_risk_escalated",
            "severity": _severity_from_attention(attention),
            "title": title,
            "message": summary,
            "dedupe_scope": f"state:{fingerprint}",
            "action_label": "Review risks",
            "action_href": "/ask",
            "ask_query": "Review all my projects and explain the combined risks that need attention.",
        },
    }


def _document_id_from_priority(priority: AgentPriority) -> int | None:
    for evidence in priority.evidence:
        if str(evidence.source_type or "").casefold() == "document" and evidence.source_id is not None:
            try:
                return int(evidence.source_id)
            except (TypeError, ValueError):
                return None
    return None


def _document_has_confirmed_followup(*, owner_id: int, document_id: int) -> bool:
    links = LifeOSContextLink.query.filter_by(
        user_id=owner_id,
        target_type="document",
        target_id=document_id,
        relation_type="derived_from",
    ).all()
    return any(link.source_type in {"task", "note"} for link in links)


def build_unhandled_followup_output(*, owner_id: int) -> dict[str, Any]:
    """Find current document findings that have not become a confirmed follow-up.

    V1 intentionally uses document-level provenance: if a confirmed task/note was
    already derived from that document, LifeOS treats the document as having an
    explicit follow-up instead of pretending it can identify completion of a
    specific prose finding with certainty.
    """

    review = run_owned_portfolio_review_agent(owner_id=owner_id)
    candidates: list[dict[str, Any]] = []
    seen_documents: set[int] = set()
    for priority in review.priorities:
        if priority.category not in {"document_risk", "document_action"}:
            continue
        document_id = _document_id_from_priority(priority)
        if document_id is None or document_id in seen_documents:
            continue
        seen_documents.add(document_id)
        if _document_has_confirmed_followup(owner_id=owner_id, document_id=document_id):
            continue
        candidates.append({
            "project_id": priority.project_id,
            "project_title": priority.project_title,
            "document_id": document_id,
            "title": priority.title,
            "reason": priority.reason,
            "recommended_action": "Review this current document finding and confirm a task or note if it still requires follow-up.",
        })
        if len(candidates) >= MAX_UNHANDLED_FINDINGS:
            break

    if candidates:
        title = f"{len(candidates)} document finding{'s' if len(candidates) != 1 else ''} still need an explicit follow-up"
        lead = candidates[0]
        summary = (
            f"{lead['project_title']} has a current document finding with no confirmed task or note derived from that document. "
            "LifeOS will not create one automatically."
        )
        fingerprint = _fingerprint([f"{item['document_id']}:{item['title']}" for item in candidates])
    else:
        title = "No unhandled document follow-up detected"
        summary = "LifeOS did not find a current document risk/action that lacks an explicit confirmed follow-up."
        fingerprint = "clear"

    return {
        "kind": "unhandled_followup",
        "title": title,
        "summary": summary,
        "attention_level": "medium" if candidates else "normal",
        "items": candidates,
        "verified_from_state": True,
        "read_only": True,
        "notification": {
            "should_notify": bool(candidates),
            "event_type": "automation.unhandled_followup",
            "severity": "medium" if candidates else "info",
            "title": title,
            "message": summary,
            "dedupe_scope": f"state:{fingerprint}",
            "action_label": "Review with LifeOS",
            "action_href": "/ask",
            "ask_query": "Which current document findings still need a concrete follow-up?",
        },
    }


def build_event_context_review_output(
    *,
    owner_id: int,
    event: LifeOSIntelligenceEvent,
) -> dict[str, Any]:
    """Enrich a chosen I14 event with its project context when available."""

    priorities: list[dict[str, Any]] = []
    attention = event.severity or "normal"
    if event.project_id is not None:
        project_review = run_owned_project_review_agent(project_id=int(event.project_id), owner_id=owner_id)
        priorities = [_priority_payload(item) for item in list(project_review.priorities)[:3]]
        attention = project_review.attention_level
    summary = event.summary or event.title
    if priorities:
        summary += f" Project context top focus: {priorities[0].get('title')}."
    return {
        "kind": "event_context_review",
        "title": event.title,
        "summary": summary,
        "attention_level": attention,
        "event": {
            "id": event.id,
            "event_type": event.event_type,
            "severity": event.severity,
            "title": event.title,
            "summary": event.summary,
            "object_type": event.object_type,
            "object_id": event.object_id,
            "project_id": event.project_id,
        },
        "project_priorities": priorities,
        "verified_from_state": True,
        "read_only": True,
        "notification": {
            "should_notify": True,
            "event_type": "automation.event_context_ready",
            "severity": _severity_from_attention(attention),
            "title": f"LifeOS reviewed: {event.title}",
            "message": summary,
            "dedupe_scope": f"source-event:{event.id}",
            "action_label": "Open Ask LifeOS",
            "action_href": "/ask",
            "ask_query": (
                f"Review my project #{event.project_id} and tell me what needs attention"
                if event.project_id is not None
                else "What should I do about the latest LifeOS event?"
            ),
        },
    }

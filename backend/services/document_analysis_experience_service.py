"""User-facing view model for the Document Brain overview experience.

This module does not call AI providers and does not alter persisted analysis.
It simply prioritises already-grounded analysis data for a calmer, more
actionable overview while leaving full detail available in the Details tab.
"""

from __future__ import annotations

from typing import Any, Iterable


_OVERVIEW_TITLES = {
    "project_plan": "Plan at a glance",
    "requirements_document": "Requirements at a glance",
    "research_paper": "Research at a glance",
    "meeting_notes": "Meeting at a glance",
    "technical_documentation": "Technical overview",
    "contract_or_policy": "Key terms at a glance",
    "general_reference": "Document at a glance",
}


def build_document_analysis_experience(
    *,
    overview: dict[str, Any] | None,
    type_workspace: dict[str, Any] | None,
    suggestions: Iterable[Any] | None,
) -> dict[str, Any]:
    """Build a presentation-only model from trusted saved analysis data."""

    safe_overview = overview if isinstance(overview, dict) else {}
    insights = safe_overview.get("analysis")
    if not isinstance(insights, dict):
        insights = {}

    workspace = type_workspace if isinstance(type_workspace, dict) else {}
    suggestion_list = list(suggestions or [])

    attention = _build_attention(insights)
    actions = _build_actions(suggestion_list, insights)
    key_points = list(insights.get("key_points") or [])[:4]
    questions = list(insights.get("questions") or [])[:4]

    populated_sections = workspace.get("populated_sections")
    if not isinstance(populated_sections, list):
        populated_sections = []

    plan_sections = [
        {
            "key": str(section.get("key") or ""),
            "label": str(section.get("label") or "Section"),
            "description": str(section.get("description") or ""),
            "preview": str(section.get("preview") or ""),
            "count": int(section.get("count") or 0),
            "source": _section_source(section),
        }
        for section in populated_sections[:6]
        if isinstance(section, dict)
    ]

    type_key = str(workspace.get("type_key") or "general_reference")
    type_label = str(
        workspace.get("type_label")
        or insights.get("document_type")
        or "Document"
    )

    metadata = workspace.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    focus_item = _pick_focus_item(actions, attention, key_points, plan_sections)
    professional_summary = _build_professional_summary(insights)

    detected_type = str(metadata.get("detected_type") or "").strip()
    confirmed_type = str(metadata.get("confirmed_type") or type_label).strip() or type_label
    type_adjusted = (
        str(metadata.get("source") or "").strip().casefold() == "user_override"
        and bool(detected_type)
        and detected_type != confirmed_type
    )

    return {
        "type_key": type_key,
        "type_label": type_label,
        "overview_title": _OVERVIEW_TITLES.get(type_key, "Document at a glance"),
        "status_label": _friendly_status(metadata),
        "confidence": str(metadata.get("confidence") or ""),
        "type_adjusted": type_adjusted,
        "detected_type": detected_type,
        "confirmed_type": confirmed_type,
        "type_adjustment_label": (
            f"{detected_type} → {confirmed_type}" if type_adjusted else ""
        ),
        "focus": focus_item["text"],
        "focus_source": focus_item.get("source") or {},
        "attention": attention[:4],
        "attention_count": len(attention),
        "actions": actions[:4],
        "action_count": len(actions),
        "key_points": key_points,
        "questions": questions,
        "plan_sections": plan_sections,
        "missing_count": len(insights.get("missing_information") or []),
        "risk_count": len(insights.get("risks") or []),
        "deadline_count": len(insights.get("deadlines") or []),
        "professional_summary": professional_summary,
    }


def _build_professional_summary(insights: dict[str, Any]) -> dict[str, Any]:
    """Build a compact professional analysis view from grounded saved data."""

    key_findings = [
        {
            "label": "Key finding",
            "title": str(item.get("title") or "").strip(),
            "detail": str(item.get("detail") or "").strip(),
            "source": item.get("source") or {},
        }
        for item in insights.get("key_points") or []
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    ][:6]

    important_details: list[dict[str, Any]] = []
    for item in insights.get("requirements") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("requirement") or "").strip()
        if title:
            important_details.append({
                "label": "Requirement",
                "title": title,
                "detail": str(item.get("details") or "").strip(),
                "source": item.get("source") or {},
            })

    for item in insights.get("decisions") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("decision") or "").strip()
        if title:
            important_details.append({
                "label": "Decision",
                "title": title,
                "detail": str(item.get("reason") or "").strip(),
                "source": item.get("source") or {},
            })

    for item in insights.get("deadlines") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("description") or "").strip()
        if title:
            date_value = str(item.get("date") or "").strip()
            important_details.append({
                "label": "Date",
                "title": title,
                "detail": f"Due {date_value}" if date_value else "",
                "source": item.get("source") or {},
            })

    risks = [
        {
            "label": "Risk",
            "title": str(item.get("risk") or "").strip(),
            "detail": str(item.get("impact") or "").strip(),
            "source": item.get("source") or {},
        }
        for item in insights.get("risks") or []
        if isinstance(item, dict) and str(item.get("risk") or "").strip()
    ][:6]

    gaps = [
        {
            "label": "Missing information",
            "title": str(item.get("question") or "").strip(),
            "detail": str(item.get("why_it_matters") or "").strip(),
            "source": item.get("source") or {},
        }
        for item in insights.get("missing_information") or []
        if isinstance(item, dict) and str(item.get("question") or "").strip()
    ][:6]

    evidence_items = (
        key_findings
        + important_details
        + risks
        + gaps
    )
    referenced = sum(
        1
        for item in evidence_items
        if isinstance(item.get("source"), dict)
        and any(item["source"].values())
    )

    return {
        "executive_summary": str(insights.get("summary") or "").strip(),
        "purpose": str(insights.get("purpose") or "").strip(),
        "key_findings": key_findings,
        "important_details": important_details[:8],
        "risks": risks,
        "gaps": gaps,
        "evidence": {
            "referenced_items": referenced,
            "total_items": len(evidence_items),
        },
    }


def _build_attention(insights: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for risk in insights.get("risks") or []:
        if not isinstance(risk, dict):
            continue
        title = str(risk.get("risk") or "").strip()
        if not title:
            continue
        items.append(
            {
                "tone": "danger",
                "label": "Risk",
                "title": title,
                "detail": str(risk.get("impact") or "").strip(),
                "source": risk.get("source") or {},
                "target": "risks",
            }
        )

    for missing in insights.get("missing_information") or []:
        if not isinstance(missing, dict):
            continue
        title = str(missing.get("question") or "").strip()
        if not title:
            continue
        items.append(
            {
                "tone": "warning",
                "label": "Information gap",
                "title": title,
                "detail": str(missing.get("why_it_matters") or "").strip(),
                "source": missing.get("source") or {},
                "target": "missing-information",
            }
        )

    for deadline in insights.get("deadlines") or []:
        if not isinstance(deadline, dict):
            continue
        title = str(deadline.get("description") or "").strip()
        if not title:
            continue
        date_value = str(deadline.get("date") or "").strip()
        items.append(
            {
                "tone": "info",
                "label": "Deadline",
                "title": title,
                "detail": f"Due {date_value}" if date_value else "Date noted in the document",
                "source": deadline.get("source") or {},
                "target": "deadlines",
            }
        )

    return items


def _build_actions(
    suggestions: list[Any],
    insights: dict[str, Any],
) -> list[dict[str, Any]]:
    pending = [
        suggestion
        for suggestion in suggestions
        if str(getattr(suggestion, "status", "")) == "Pending"
    ]

    if pending:
        return [
            {
                "title": str(getattr(item, "title", "") or "").strip(),
                "detail": str(getattr(item, "description", "") or "").strip(),
                "priority": str(getattr(item, "priority", "Medium") or "Medium"),
                "deadline": (
                    item.deadline.isoformat()
                    if getattr(item, "deadline", None)
                    else ""
                ),
                "source": getattr(item, "source", {}) or {},
                "persisted": True,
            }
            for item in pending
            if str(getattr(item, "title", "") or "").strip()
        ]

    actions: list[dict[str, Any]] = []
    for item in insights.get("action_items") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        actions.append(
            {
                "title": title,
                "detail": str(item.get("description") or "").strip(),
                "priority": str(item.get("priority") or "Medium"),
                "deadline": str(item.get("deadline") or ""),
                "source": item.get("source") or {},
                "persisted": False,
            }
        )

    return actions


def _pick_focus_item(
    actions: list[dict[str, Any]],
    attention: list[dict[str, Any]],
    key_points: list[dict[str, Any]],
    plan_sections: list[dict[str, Any]],
) -> dict[str, Any]:
    if actions:
        return {
            "text": actions[0]["title"],
            "source": actions[0].get("source") or {},
        }
    if attention:
        return {
            "text": attention[0]["title"],
            "source": attention[0].get("source") or {},
        }
    if key_points:
        return {
            "text": str(key_points[0].get("title") or "").strip(),
            "source": key_points[0].get("source") or {},
        }
    if plan_sections:
        return {
            "text": plan_sections[0]["preview"] or plan_sections[0]["label"],
            "source": plan_sections[0].get("source") or {},
        }
    return {
        "text": "Review the grounded analysis and decide the next useful action.",
        "source": {},
    }


def _section_source(section: dict[str, Any]) -> dict[str, Any]:
    """Return one representative source for a compact overview section."""

    value = section.get("value")
    if isinstance(value, dict):
        source = value.get("source")
        if isinstance(source, dict) and any(source.values()):
            return source

    items = section.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            source = item.get("source")
            if isinstance(source, dict) and any(source.values()):
                return source

    return {}


def _friendly_status(metadata: dict[str, Any]) -> str:
    source = str(metadata.get("source") or "").strip().casefold()
    if source in {"detected_confirmed", "user_confirmed"}:
        return "Type confirmed"
    if source == "user_override":
        return "Type adjusted"
    return "Analysis saved"

"""I12 — verified Intelligence-powered Home / Today.

Home is a product aggregation layer over intelligence capabilities that already
exist in LifeOS.  It does not introduce a second reasoning pipeline and it does
not call an LLM.  Every section is built from owned, trusted application state:
I8 priorities, I10 activity, and I11 workspace insights.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from services.intelligence_workspace_query_service import (
    WorkspaceInsightResult,
    build_owned_deadline_insight,
    build_owned_document_review_insight,
    build_owned_study_next_insight,
)
from services.lifeos_activity_service import RecentActivityResult, build_owned_recent_activity
from services.today_intelligence_service import TodayIntelligenceResult, build_owned_today_intelligence


HOME_ACTIVITY_LIMIT = 5
HOME_SECTION_ITEM_LIMIT = 3


@dataclass(frozen=True)
class HomeSignal:
    key: str
    label: str
    count: int
    tone: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "count": self.count,
            "tone": self.tone,
        }


@dataclass(frozen=True)
class HomeBriefing:
    headline: str
    summary: str
    attention_level: str
    signals: tuple[HomeSignal, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "headline": self.headline,
            "summary": self.summary,
            "attention_level": self.attention_level,
            "signals": [item.to_dict() for item in self.signals],
        }


@dataclass(frozen=True)
class HomeIntelligenceResult:
    today: date
    briefing: HomeBriefing
    focus: TodayIntelligenceResult
    deadlines: WorkspaceInsightResult
    documents: WorkspaceInsightResult
    study: WorkspaceInsightResult
    activity: RecentActivityResult

    @property
    def context_limited(self) -> bool:
        return any((
            self.focus.context_limited,
            self.deadlines.context_limited,
            self.documents.context_limited,
            self.study.context_limited,
            self.activity.context_limited,
        ))

    def to_dict(self) -> dict[str, Any]:
        return {
            "today": self.today.isoformat(),
            "briefing": self.briefing.to_dict(),
            "focus": self.focus.to_dict(),
            "deadlines": _bounded_insight(self.deadlines),
            "documents": _bounded_insight(self.documents),
            "study": _bounded_insight(self.study),
            "activity": _bounded_activity(self.activity),
            "context_limited": self.context_limited,
            "verified_from_state": True,
            "read_only": True,
        }


def _bounded_insight(result: WorkspaceInsightResult) -> dict[str, Any]:
    payload = result.to_dict()
    payload["items"] = payload.get("items", [])[:HOME_SECTION_ITEM_LIMIT]
    counts = dict(payload.get("counts") or {})
    counts["shown_on_home"] = len(payload["items"])
    payload["counts"] = counts
    return payload


def _bounded_activity(result: RecentActivityResult) -> dict[str, Any]:
    payload = result.to_dict()
    payload["items"] = payload.get("items", [])[:HOME_ACTIVITY_LIMIT]
    return payload


def _briefing(
    *,
    focus: TodayIntelligenceResult,
    deadlines: WorkspaceInsightResult,
    documents: WorkspaceInsightResult,
    study: WorkspaceInsightResult,
    activity: RecentActivityResult,
) -> HomeBriefing:
    high = sum(item.severity == "high" for item in focus.priorities)
    priority_count = len(focus.priorities)
    deadline_count = int(deadlines.counts.get("matched", 0) or 0)
    document_count = int(documents.counts.get("matched", 0) or 0)
    activity_count = int(activity.total_items or 0)

    if high:
        headline = f"{high} high-attention item{'s' if high != 1 else ''} need your focus today"
    elif priority_count:
        headline = f"{priority_count} ranked priorit{'ies' if priority_count != 1 else 'y'} for today"
    elif deadline_count or document_count:
        headline = "Your workspace is stable, with a few items worth reviewing"
    else:
        headline = "Your workspace looks clear today"

    parts: list[str] = []
    if deadline_count:
        parts.append(f"{deadline_count} upcoming deadline{'s' if deadline_count != 1 else ''}")
    if document_count:
        parts.append(f"{document_count} document{'s' if document_count != 1 else ''} need analysis attention")
    if activity_count:
        parts.append(f"{activity_count} recent change{'s' if activity_count != 1 else ''} recorded today")

    if parts:
        summary = ". ".join(part[:1].upper() + part[1:] for part in parts) + "."
    elif priority_count:
        summary = focus.summary
    elif study.items:
        summary = f"No urgent execution signal is ahead of your normal work. {study.summary}"
    else:
        summary = "LifeOS did not find a current blocker, near deadline, stale analysis, or other verified attention signal."

    signals = (
        HomeSignal("focus", "Priorities", priority_count, "danger" if high else "accent" if priority_count else "quiet"),
        HomeSignal("deadlines", "Next 7 days", deadline_count, "warning" if deadline_count else "quiet"),
        HomeSignal("documents", "Docs to review", document_count, "warning" if document_count else "quiet"),
        HomeSignal("activity", "Changes today", activity_count, "accent" if activity_count else "quiet"),
    )
    return HomeBriefing(
        headline=headline,
        summary=summary,
        attention_level=focus.attention_level,
        signals=signals,
    )


def build_owned_home_intelligence(
    *,
    owner_id: int,
    today: date | None = None,
    now: datetime | None = None,
) -> HomeIntelligenceResult:
    """Build the full I12 Home packet without mutating state or invoking AI."""

    effective_today = today or date.today()
    focus = build_owned_today_intelligence(owner_id=owner_id, today=effective_today)
    deadlines = build_owned_deadline_insight(
        owner_id=owner_id,
        query="What deadlines are coming up in the next 7 days?",
        today=effective_today,
    )
    documents = build_owned_document_review_insight(owner_id=owner_id)
    study = build_owned_study_next_insight(owner_id=owner_id, today=effective_today)
    activity = build_owned_recent_activity(
        owner_id=owner_id,
        query="What changed today?",
        now=now,
        limit=HOME_ACTIVITY_LIMIT,
    )
    return HomeIntelligenceResult(
        today=effective_today,
        briefing=_briefing(
            focus=focus,
            deadlines=deadlines,
            documents=documents,
            study=study,
            activity=activity,
        ),
        focus=focus,
        deadlines=deadlines,
        documents=documents,
        study=study,
        activity=activity,
    )

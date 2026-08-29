"""Verified, read-only Today intelligence for the LifeOS home dashboard.

This service intentionally reuses the constrained I8 portfolio review agent.
It does not call an LLM and it does not mutate application state.  The goal is
simple: turn the trusted project/task/document state LifeOS already knows into
one bounded, ranked list of what deserves attention *today*.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from services.intelligence_context_service import ContextEvidence
from services.intelligence_action_service import priority_action_options
from services.project_review_agent_service import AgentPriority, run_owned_portfolio_review_agent


MAX_TODAY_PRIORITIES = 5


@dataclass(frozen=True)
class TodayPriority:
    project_id: int
    project_title: str
    category: str
    severity: str
    title: str
    reason: str
    recommended_action: str
    evidence: tuple[ContextEvidence, ...]

    @classmethod
    def from_agent_priority(cls, item: AgentPriority) -> "TodayPriority":
        return cls(
            project_id=item.project_id,
            project_title=item.project_title,
            category=item.category,
            severity=item.severity,
            title=item.title,
            reason=item.reason,
            recommended_action=item.recommended_action,
            evidence=item.evidence,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_title": self.project_title,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "reason": self.reason,
            "recommended_action": self.recommended_action,
            "actions": priority_action_options({
                "category": self.category,
                "severity": self.severity,
            }),
            "evidence": [
                {
                    "source_type": item.source_type,
                    "source_id": item.source_id,
                    "label": item.label,
                    "field": item.field,
                    "freshness": item.freshness,
                }
                for item in self.evidence
            ],
        }


@dataclass(frozen=True)
class TodayIntelligenceResult:
    today: date
    attention_level: str
    summary: str
    priorities: tuple[TodayPriority, ...]
    total_owned_projects: int
    reviewed_projects: int
    context_limited: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "today": self.today.isoformat(),
            "attention_level": self.attention_level,
            "summary": self.summary,
            "priorities": [item.to_dict() for item in self.priorities],
            "counts": {
                "total_owned_projects": self.total_owned_projects,
                "reviewed_projects": self.reviewed_projects,
                "ranked_priorities": len(self.priorities),
                "high": sum(item.severity == "high" for item in self.priorities),
                "medium": sum(item.severity == "medium" for item in self.priorities),
                "low": sum(item.severity == "low" for item in self.priorities),
            },
            "context_limited": self.context_limited,
            "verified_from_state": True,
            "read_only": True,
        }


def _summary(*, priorities: tuple[TodayPriority, ...], project_count: int, limited: bool) -> str:
    if not project_count:
        return "Create your first project to give LifeOS enough workspace state to build a daily attention view."

    if not priorities:
        return "LifeOS did not find a blocked task, overdue item, near deadline, stale document warning, or other ranked project action that needs attention right now."

    high_count = sum(item.severity == "high" for item in priorities)
    lead = priorities[0]
    if high_count:
        text = (
            f"{high_count} high-attention item{'s' if high_count != 1 else ''} need focus. "
            f"Start with {lead.title}."
        )
    else:
        text = f"Your workspace is stable overall. The clearest next focus is {lead.title}."

    if limited:
        text += " LifeOS reviewed the bounded project context allowed by your current resource limits."
    return text


def build_owned_today_intelligence(*, owner_id: int, today: date | None = None) -> TodayIntelligenceResult:
    effective_today = today or date.today()
    portfolio = run_owned_portfolio_review_agent(owner_id=owner_id, today=effective_today)
    selected = tuple(
        TodayPriority.from_agent_priority(item)
        for item in portfolio.priorities[:MAX_TODAY_PRIORITIES]
    )

    return TodayIntelligenceResult(
        today=effective_today,
        attention_level=portfolio.attention_level,
        summary=_summary(
            priorities=selected,
            project_count=portfolio.total_owned_projects,
            limited=portfolio.context_limited,
        ),
        priorities=selected,
        total_owned_projects=portfolio.total_owned_projects,
        reviewed_projects=portfolio.reviewed_projects,
        context_limited=portfolio.context_limited,
    )

"""Verified read-only portfolio review for Ask LifeOS.

This workflow summarizes *owned* projects by reusing the same trusted project
context and deterministic review services used by the single-project path.  It
never gives the model direct database access and currently produces a fully
deterministic workspace-level answer so a request such as "all projects" can be
answered without inventing cross-project state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.intelligence_context_service import collect_owned_project_context
from services.project_review_intelligence_service import review_project_context
from services.project_service import list_owned_projects


MAX_PORTFOLIO_PROJECTS = 12
_ATTENTION_RANK = {"high": 3, "medium": 2, "normal": 1, "low": 0}


@dataclass(frozen=True)
class PortfolioProjectSummary:
    project_id: int
    title: str
    status: str | None
    priority: str | None
    manual_progress: int
    task_progress: int
    total_tasks: int
    completed_tasks: int
    overdue_tasks: int
    blocked_tasks: int
    due_soon_tasks: int
    current_documents: int
    stale_document_analyses: int
    attention_level: str
    top_signal: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "status": self.status,
            "priority": self.priority,
            "manual_progress": self.manual_progress,
            "task_progress": self.task_progress,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "overdue_tasks": self.overdue_tasks,
            "blocked_tasks": self.blocked_tasks,
            "due_soon_tasks": self.due_soon_tasks,
            "current_documents": self.current_documents,
            "stale_document_analyses": self.stale_document_analyses,
            "attention_level": self.attention_level,
            "top_signal": self.top_signal,
        }


@dataclass(frozen=True)
class PortfolioReviewResult:
    projects: tuple[PortfolioProjectSummary, ...]
    total_owned_projects: int
    reviewed_projects: int
    high_attention_projects: int
    medium_attention_projects: int
    normal_attention_projects: int
    context_limited: bool

    @property
    def attention_level(self) -> str:
        if self.high_attention_projects:
            return "high"
        if self.medium_attention_projects:
            return "medium"
        return "normal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "projects": [item.to_dict() for item in self.projects],
            "total_owned_projects": self.total_owned_projects,
            "reviewed_projects": self.reviewed_projects,
            "high_attention_projects": self.high_attention_projects,
            "medium_attention_projects": self.medium_attention_projects,
            "normal_attention_projects": self.normal_attention_projects,
            "context_limited": self.context_limited,
            "attention_level": self.attention_level,
            "read_only": True,
        }


def _facts(review) -> dict[str, Any]:
    return {str(item.get("key")): item.get("value") for item in review.facts}


def review_owned_portfolio(*, owner_id: int) -> PortfolioReviewResult:
    owned = list_owned_projects(int(owner_id))
    selected = owned[:MAX_PORTFOLIO_PROJECTS]
    summaries: list[PortfolioProjectSummary] = []

    for project in selected:
        context = collect_owned_project_context(project_id=project.id, owner_id=owner_id)
        review = review_project_context(context=context)
        facts = _facts(review)
        summaries.append(
            PortfolioProjectSummary(
                project_id=int(project.id),
                title=str(project.title or f"Project {project.id}"),
                status=facts.get("project.status"),
                priority=facts.get("project.priority"),
                manual_progress=int(facts.get("project.manual_progress") or 0),
                task_progress=int(facts.get("project.task_progress") or 0),
                total_tasks=int(facts.get("project.total_tasks") or 0),
                completed_tasks=int(facts.get("project.completed_tasks") or 0),
                overdue_tasks=int(facts.get("project.overdue_tasks") or 0),
                blocked_tasks=int(facts.get("project.blocked_tasks") or 0),
                due_soon_tasks=int(facts.get("project.due_soon_tasks") or 0),
                current_documents=int(facts.get("project.current_documents") or 0),
                stale_document_analyses=int(facts.get("project.stale_document_analyses") or 0),
                attention_level=review.attention_level,
                top_signal=review.signals[0].title if review.signals else None,
            )
        )

    # Put the projects needing attention first while keeping the current product
    # order as a stable tiebreaker (Python sort is stable).
    summaries.sort(key=lambda item: -_ATTENTION_RANK.get(item.attention_level, 0))

    return PortfolioReviewResult(
        projects=tuple(summaries),
        total_owned_projects=len(owned),
        reviewed_projects=len(summaries),
        high_attention_projects=sum(item.attention_level == "high" for item in summaries),
        medium_attention_projects=sum(item.attention_level == "medium" for item in summaries),
        normal_attention_projects=sum(item.attention_level == "normal" for item in summaries),
        context_limited=len(owned) > len(selected),
    )


def build_deterministic_portfolio_answer(result: PortfolioReviewResult) -> str:
    if not result.total_owned_projects:
        return "You do not have any projects in LifeOS yet."

    intro = (
        f"You have {result.total_owned_projects} project"
        f"{'s' if result.total_owned_projects != 1 else ''}. "
        f"{result.high_attention_projects} need high attention, "
        f"{result.medium_attention_projects} need medium attention, and "
        f"{result.normal_attention_projects} currently look normal."
    )

    details: list[str] = []
    for item in result.projects[:6]:
        task_state = (
            f"{item.completed_tasks}/{item.total_tasks} tasks completed"
            if item.total_tasks
            else "no project tasks"
        )
        alerts: list[str] = []
        if item.overdue_tasks:
            alerts.append(f"{item.overdue_tasks} overdue")
        if item.blocked_tasks:
            alerts.append(f"{item.blocked_tasks} blocked")
        if item.due_soon_tasks:
            alerts.append(f"{item.due_soon_tasks} due soon")
        if item.stale_document_analyses:
            alerts.append(f"{item.stale_document_analyses} stale document analysis")
        suffix = f"; {', '.join(alerts)}" if alerts else ""
        details.append(
            f"{item.title}: {item.status or 'No status'}, {item.manual_progress}% saved progress, "
            f"{task_state}{suffix}."
        )

    limited = (
        f" I reviewed the {result.reviewed_projects} most recent projects because the workspace contains more than the portfolio review limit."
        if result.context_limited
        else ""
    )
    return " ".join([intro, *details]).strip() + limited

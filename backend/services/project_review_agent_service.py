"""I8 constrained Project Review Agent for LifeOS.

The agent is deliberately read-only. It does not let an LLM choose arbitrary
LifeOS tools and it never writes to application state. Instead it reuses the
reviewed project tool plan/context, derives evidence-backed priorities, ranks
them deterministically, and exposes exactly why each recommendation exists.

This is the first agentic workflow in LifeOS: inspect -> prioritize -> recommend
-> verify from trusted state. Action execution is intentionally deferred to the
future confirmation/action boundary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from services.intelligence_context_service import ContextEvidence, IntelligenceContextPacket, collect_owned_project_context
from services.project_review_intelligence_service import ProjectReviewResult, review_project_context
from services.project_service import list_owned_projects


MAX_AGENT_PRIORITIES_PER_PROJECT = 8
MAX_PORTFOLIO_AGENT_PROJECTS = 12
MAX_PORTFOLIO_PRIORITIES = 8

_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}
_PRIORITY_RANK = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}


@dataclass(frozen=True)
class AgentPriority:
    project_id: int
    project_title: str
    category: str
    severity: str
    score: int
    title: str
    reason: str
    recommended_action: str
    evidence: tuple[ContextEvidence, ...]

    def to_dict(self, *, include_diagnostics: bool = False) -> dict[str, Any]:
        payload = {
            "project_id": self.project_id,
            "project_title": self.project_title,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "reason": self.reason,
            "recommended_action": self.recommended_action,
            "evidence": [asdict(item) for item in self.evidence],
        }
        if include_diagnostics:
            payload["score"] = self.score
        return payload


@dataclass(frozen=True)
class ProjectReviewAgentResult:
    project_id: int
    project_title: str
    attention_level: str
    priorities: tuple[AgentPriority, ...]
    reviewed_steps: tuple[str, ...]
    context_limited: bool

    def to_dict(self, *, include_diagnostics: bool = False) -> dict[str, Any]:
        payload = {
            "kind": "project_review_agent",
            "project_id": self.project_id,
            "project_title": self.project_title,
            "attention_level": self.attention_level,
            "priorities": [item.to_dict(include_diagnostics=include_diagnostics) for item in self.priorities],
            "context_limited": self.context_limited,
            "read_only": True,
        }
        if include_diagnostics:
            payload["reviewed_steps"] = list(self.reviewed_steps)
        return payload


@dataclass(frozen=True)
class PortfolioReviewAgentResult:
    total_owned_projects: int
    reviewed_projects: int
    priorities: tuple[AgentPriority, ...]
    attention_level: str
    context_limited: bool

    def to_dict(self, *, include_diagnostics: bool = False) -> dict[str, Any]:
        return {
            "kind": "portfolio_review_agent",
            "total_owned_projects": self.total_owned_projects,
            "reviewed_projects": self.reviewed_projects,
            "priorities": [item.to_dict(include_diagnostics=include_diagnostics) for item in self.priorities],
            "attention_level": self.attention_level,
            "context_limited": self.context_limited,
            "read_only": True,
        }


def _task_evidence(task: dict[str, Any]) -> tuple[ContextEvidence, ...]:
    return (
        ContextEvidence(
            source_type="task",
            source_id=task.get("id"),
            label=str(task.get("title") or "Project task"),
            field="status/deadline/priority",
        ),
    )


def _document_evidence(document: dict[str, Any], field: str = "analysis_status") -> tuple[ContextEvidence, ...]:
    return (
        ContextEvidence(
            source_type="document",
            source_id=document.get("id"),
            label=str(document.get("filename") or "Project document"),
            field=field,
            freshness=(
                "current"
                if document.get("analysis_status") == "Current"
                else "stale_or_unanalysed"
            ),
        ),
    )


def _project_evidence(project_id: int, field: str) -> tuple[ContextEvidence, ...]:
    return (
        ContextEvidence(
            source_type="project",
            source_id=project_id,
            label="Project state",
            field=field,
        ),
    )


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _priority_sort_key(item: AgentPriority) -> tuple[Any, ...]:
    return (
        -int(item.score),
        -_SEVERITY_RANK.get(item.severity, 0),
        item.project_title.casefold(),
        item.title.casefold(),
    )


def _add_priority(items: list[AgentPriority], item: AgentPriority, seen: set[tuple[Any, ...]]) -> None:
    key = (item.project_id, item.category, item.title.casefold())
    if key in seen:
        return
    seen.add(key)
    items.append(item)


def _trusted_document_priorities(
    *,
    document: dict[str, Any],
    project_id: int,
    project_title: str,
) -> list[AgentPriority]:
    """Turn only *current* structured document findings into agent priorities."""

    if document.get("analysis_status") != "Current":
        return []
    analysis = document.get("trusted_analysis")
    if not isinstance(analysis, dict):
        return []

    priorities: list[AgentPriority] = []
    filename = str(document.get("filename") or "Project document")

    for risk in list(analysis.get("risks") or [])[:2]:
        if not isinstance(risk, dict):
            continue
        text = _clean_text(risk.get("text") or risk.get("detail"))
        detail = _clean_text(risk.get("detail") or risk.get("text"))
        if not text:
            continue
        priorities.append(
            AgentPriority(
                project_id=project_id,
                project_title=project_title,
                category="document_risk",
                severity="medium",
                score=68,
                title=f"Review documented risk: {text}",
                reason=(
                    f"{filename} contains a current structured risk finding. "
                    + (detail if detail and detail != text else "LifeOS is treating it as current document intelligence.")
                ),
                recommended_action="Review the risk and decide whether it needs a concrete task, owner, or mitigation.",
                evidence=_document_evidence(document, "trusted_analysis.risks"),
            )
        )

    for action in list(analysis.get("action_items") or [])[:2]:
        if not isinstance(action, dict):
            continue
        text = _clean_text(action.get("text") or action.get("detail"))
        detail = _clean_text(action.get("detail") or action.get("text"))
        if not text:
            continue
        priorities.append(
            AgentPriority(
                project_id=project_id,
                project_title=project_title,
                category="document_action",
                severity="medium",
                score=58,
                title=f"Review document action: {text}",
                reason=(
                    f"{filename} contains a current action-item finding. "
                    + (detail if detail and detail != text else "It has not been promoted into trusted application state automatically.")
                ),
                recommended_action="Confirm whether this document action should become a real LifeOS task.",
                evidence=_document_evidence(document, "trusted_analysis.action_items"),
            )
        )

    for missing in list(analysis.get("missing_information") or [])[:1]:
        if not isinstance(missing, dict):
            continue
        text = _clean_text(missing.get("text") or missing.get("detail"))
        if not text:
            continue
        priorities.append(
            AgentPriority(
                project_id=project_id,
                project_title=project_title,
                category="missing_information",
                severity="low",
                score=44,
                title=f"Resolve missing information: {text}",
                reason=f"{filename} currently identifies this as missing information.",
                recommended_action="Decide whether this gap blocks a decision or can remain unresolved for now.",
                evidence=_document_evidence(document, "trusted_analysis.missing_information"),
            )
        )

    return priorities


def review_project_with_agent(
    *,
    context: IntelligenceContextPacket,
    review: ProjectReviewResult | None = None,
    today: date | None = None,
) -> ProjectReviewAgentResult:
    """Run the constrained prioritization pass over one trusted project snapshot."""

    if context.scope_type != "project":
        raise ValueError("Project Review Agent requires project-scoped trusted context.")

    effective_today = today or date.today()
    active_review = review or review_project_context(context=context, today=effective_today)
    project_id = int(context.scope_id)
    project_title = str(context.scope_label or f"Project {project_id}")
    tool_data = context.tool_data
    project_state = tool_data.get("project_state") or {}
    project = project_state.get("project") or {}
    tasks = list((tool_data.get("tasks") or {}).get("tasks") or [])
    documents = list((tool_data.get("documents") or {}).get("documents") or [])

    priorities: list[AgentPriority] = []
    seen: set[tuple[Any, ...]] = set()

    # 1) Hard blockers and overdue work always dominate the queue.
    open_tasks = [task for task in tasks if str(task.get("status") or "") != "Completed"]
    for task in open_tasks:
        deadline = _parse_date(task.get("deadline"))
        status = str(task.get("status") or "Pending")
        title = str(task.get("title") or "Untitled task")
        priority_bonus = _PRIORITY_RANK.get(str(task.get("priority") or ""), 0) * 2

        if status == "Blocked":
            _add_priority(
                priorities,
                AgentPriority(
                    project_id, project_title, "blocked_task", "high", 100 + priority_bonus,
                    f"Unblock: {title}",
                    "This task is explicitly marked Blocked in LifeOS.",
                    "Identify the blocking dependency or decision before adding more work behind it.",
                    _task_evidence(task),
                ),
                seen,
            )
            continue

        if deadline and deadline < effective_today:
            days_overdue = (effective_today - deadline).days
            _add_priority(
                priorities,
                AgentPriority(
                    project_id, project_title, "overdue_task", "high", 94 + min(days_overdue, 12) + priority_bonus,
                    f"Triage overdue task: {title}",
                    f"The task is still open and its deadline was {deadline.isoformat()} ({days_overdue} day{'s' if days_overdue != 1 else ''} ago).",
                    "Complete it, deliberately reschedule it, or remove it if it is no longer required.",
                    _task_evidence(task),
                ),
                seen,
            )
            continue

        if deadline:
            days = (deadline - effective_today).days
            if 0 <= days <= 7:
                severity = "high" if days <= 2 else "medium"
                score = (88 if days <= 2 else 78) + max(0, 7 - days) + priority_bonus
                _add_priority(
                    priorities,
                    AgentPriority(
                        project_id, project_title, "due_soon_task", severity, score,
                        f"Protect deadline: {title}",
                        f"This open task is due on {deadline.isoformat()} ({days} day{'s' if days != 1 else ''} remaining).",
                        "Reserve time for this task before lower-urgency work.",
                        _task_evidence(task),
                    ),
                    seen,
                )

    # 2) Project-level deadline is verified application state, not an LLM guess.
    project_deadline = _parse_date(project.get("deadline"))
    if project_deadline:
        days = (project_deadline - effective_today).days
        if days < 0:
            _add_priority(
                priorities,
                AgentPriority(
                    project_id, project_title, "project_deadline", "high", 97,
                    "Review the overdue project deadline",
                    f"The saved project deadline was {project_deadline.isoformat()} and has passed.",
                    "Confirm whether the deadline should be updated and identify any unfinished deliverables.",
                    _project_evidence(project_id, "deadline"),
                ),
                seen,
            )
        elif days <= 7:
            _add_priority(
                priorities,
                AgentPriority(
                    project_id, project_title, "project_deadline", "high" if days <= 2 else "medium", 86 + max(0, 7 - days),
                    "Protect the project deadline",
                    f"The saved project deadline is {project_deadline.isoformat()} ({days} day{'s' if days != 1 else ''} remaining).",
                    "Check the remaining tasks and make sure the critical path fits inside the available time.",
                    _project_evidence(project_id, "deadline"),
                ),
                seen,
            )

    # 3) Stale/unanalysed intelligence is never treated as current evidence.
    stale_documents = [item for item in documents if item.get("analysis_status") == "Stale"]
    for document in stale_documents[:2]:
        _add_priority(
            priorities,
            AgentPriority(
                project_id, project_title, "stale_document", "medium", 66,
                f"Refresh stale intelligence: {document.get('filename')}",
                "The document changed after its saved analysis, so LifeOS is refusing to treat the old findings as current.",
                "Re-run analysis when this document matters to a current project decision.",
                _document_evidence(document),
            ),
            seen,
        )

    # 4) Current structured document findings may inform a recommendation, but
    # they never directly create tasks or mutate project state.
    for document in documents:
        for item in _trusted_document_priorities(
            document=document,
            project_id=project_id,
            project_title=project_title,
        ):
            _add_priority(priorities, item, seen)

    # 5) Keep momentum when there is no urgent work. This is deliberately lower
    # priority than verified deadlines, blockers, and document risks.
    if open_tasks and not any(item.category in {"blocked_task", "overdue_task", "due_soon_task"} for item in priorities):
        next_task = sorted(
            open_tasks,
            key=lambda task: (
                -_PRIORITY_RANK.get(str(task.get("priority") or ""), 0),
                -(float(task.get("priority_score") or 0)),
                int(task.get("id") or 0),
            ),
        )[0]
        _add_priority(
            priorities,
            AgentPriority(
                project_id, project_title, "next_task", "low", 38,
                f"Continue: {next_task.get('title')}",
                "There is no higher-urgency task-state warning, so this is the strongest current open-task candidate from LifeOS state.",
                "Make this the next concrete unit of work unless you intentionally choose another priority.",
                _task_evidence(next_task),
            ),
            seen,
        )
    elif not open_tasks and str(project.get("status") or "").casefold() not in {"completed", "complete", "archived"}:
        _add_priority(
            priorities,
            AgentPriority(
                project_id, project_title, "missing_next_action", "low", 42,
                "Define the next concrete project task",
                "The project is active but LifeOS has no open project tasks to use as an execution queue.",
                "Add one concrete next action so progress can be measured from work rather than only a manual percentage.",
                _project_evidence(project_id, "status"),
            ),
            seen,
        )

    priorities.sort(key=_priority_sort_key)
    priorities = priorities[:MAX_AGENT_PRIORITIES_PER_PROJECT]

    attention = active_review.attention_level
    if priorities and priorities[0].severity == "high":
        attention = "high"
    elif priorities and priorities[0].severity == "medium" and attention == "normal":
        attention = "medium"

    return ProjectReviewAgentResult(
        project_id=project_id,
        project_title=project_title,
        attention_level=attention,
        priorities=tuple(priorities),
        reviewed_steps=(
            "inspect_project_state",
            "inspect_tasks_and_deadlines",
            "inspect_document_freshness",
            "inspect_current_document_findings",
            "rank_priorities",
        ),
        context_limited=bool(context.context_limited or active_review.context_limited),
    )


def run_owned_project_review_agent(*, project_id: int, owner_id: int, today: date | None = None) -> ProjectReviewAgentResult:
    context = collect_owned_project_context(project_id=project_id, owner_id=owner_id)
    review = review_project_context(context=context, today=today)
    return review_project_with_agent(context=context, review=review, today=today)


def run_owned_portfolio_review_agent(*, owner_id: int, today: date | None = None) -> PortfolioReviewAgentResult:
    owned = list_owned_projects(int(owner_id))
    selected = owned[:MAX_PORTFOLIO_AGENT_PROJECTS]
    priorities: list[AgentPriority] = []
    top_attention = "normal"
    limited = len(owned) > len(selected)

    for project in selected:
        context = collect_owned_project_context(project_id=project.id, owner_id=owner_id)
        review = review_project_context(context=context, today=today)
        agent = review_project_with_agent(context=context, review=review, today=today)
        priorities.extend(agent.priorities)
        limited = limited or agent.context_limited
        if _SEVERITY_RANK.get(agent.attention_level, 0) > _SEVERITY_RANK.get(top_attention, 0):
            top_attention = agent.attention_level

    priorities.sort(key=_priority_sort_key)
    priorities = priorities[:MAX_PORTFOLIO_PRIORITIES]
    if priorities:
        if priorities[0].severity == "high":
            top_attention = "high"
        elif priorities[0].severity == "medium" and top_attention == "normal":
            top_attention = "medium"

    return PortfolioReviewAgentResult(
        total_owned_projects=len(owned),
        reviewed_projects=len(selected),
        priorities=tuple(priorities),
        attention_level=top_attention,
        context_limited=limited,
    )


def build_project_agent_answer(result: ProjectReviewAgentResult) -> str:
    """Concise human summary; structured priority cards carry the detail.

    The API already returns every evidence-backed priority in ``agent.priorities``.
    Repeating the same reasons/actions in ``answer`` made Ask LifeOS feel like a
    raw data dump, so the prose now acts only as an executive summary.
    """

    if not result.priorities:
        return f"{result.project_title} does not currently show a concrete priority that needs attention from the trusted project state I reviewed."

    count = len(result.priorities)
    summary = (
        f"I reviewed {result.project_title} and found {count} ranked "
        f"priorit{'y' if count == 1 else 'ies'}. "
        f"Top focus: {result.priorities[0].title}."
    )
    if result.context_limited:
        summary += " Some project context was capped by LifeOS limits, so this review may not be exhaustive."
    return summary


def build_portfolio_agent_answer(result: PortfolioReviewAgentResult) -> str:
    """Concise portfolio summary; the UI renders ranked priorities separately."""

    if not result.total_owned_projects:
        return "You do not have any projects in LifeOS yet."
    if not result.priorities:
        return (
            f"I reviewed {result.reviewed_projects} project{'s' if result.reviewed_projects != 1 else ''} and did not find a concrete blocker, overdue item, near deadline, stale document warning, or other ranked next action in the trusted state."
        )

    count = len(result.priorities)
    summary = (
        f"I reviewed {result.reviewed_projects} of your {result.total_owned_projects} project"
        f"{'s' if result.total_owned_projects != 1 else ''} and found {count} ranked "
        f"priorit{'y' if count == 1 else 'ies'}. "
        f"Top focus: {result.priorities[0].project_title} — {result.priorities[0].title}."
    )
    if result.context_limited:
        summary += " The portfolio review was capped by LifeOS context limits, so lower-ranked items may exist outside this review."
    return summary

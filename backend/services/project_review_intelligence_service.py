"""First reliable LifeOS Intelligence workflow: read-only Project Review.

The review intentionally uses deterministic state and reviewed tools before any
future LLM reasoning layer. Facts, inferences and suggestions remain visibly
separate. It never writes to the database.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from services.intelligence_context_service import (
    ContextEvidence,
    IntelligenceContextPacket,
    build_project_context_packet,
)
from services.intelligence_executor_service import execute_intelligence_plan
from services.intelligence_planner_service import plan_project_review
from services.intelligence_tool_registry_service import (
    DEFAULT_INTELLIGENCE_TOOL_REGISTRY,
    IntelligenceToolRegistry,
)


@dataclass(frozen=True)
class ReviewSignal:
    kind: str
    severity: str
    title: str
    detail: str
    evidence: tuple[ContextEvidence, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "evidence": [asdict(item) for item in self.evidence],
        }


@dataclass(frozen=True)
class ProjectReviewResult:
    project: dict[str, Any]
    attention_level: str
    summary: str
    facts: tuple[dict[str, Any], ...]
    signals: tuple[ReviewSignal, ...]
    suggestions: tuple[ReviewSignal, ...]
    context_limited: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "attention_level": self.attention_level,
            "summary": self.summary,
            "facts": list(self.facts),
            "signals": [item.to_dict() for item in self.signals],
            "suggestions": [item.to_dict() for item in self.suggestions],
            "context_limited": self.context_limited,
            "read_only": True,
        }


def _task_evidence(task: dict[str, Any]) -> tuple[ContextEvidence, ...]:
    return (
        ContextEvidence(
            source_type="task",
            source_id=task.get("id"),
            label=task.get("title") or "Project task",
            field="status/deadline/priority",
        ),
    )


def _document_evidence(document: dict[str, Any]) -> tuple[ContextEvidence, ...]:
    return (
        ContextEvidence(
            source_type="document",
            source_id=document.get("id"),
            label=document.get("filename") or "Project document",
            field="analysis_status",
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


def _priority_rank(value: str) -> int:
    return {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}.get(value, 0)


def _select_attention_tasks(tasks: list[dict[str, Any]], *, today: date) -> list[dict[str, Any]]:
    open_tasks = [task for task in tasks if task.get("status") != "Completed"]

    def parsed_deadline(task: dict[str, Any]) -> date | None:
        value = task.get("deadline")
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    def key(task: dict[str, Any]) -> tuple[Any, ...]:
        deadline = parsed_deadline(task)
        overdue = bool(deadline and deadline < today)
        blocked = task.get("status") == "Blocked"
        return (
            not overdue,
            not blocked,
            deadline is None,
            deadline or date.max,
            -_priority_rank(str(task.get("priority") or "")),
            -(float(task.get("priority_score") or 0)),
            int(task.get("id") or 0),
        )

    return sorted(open_tasks, key=key)[:5]


def _attention_level(*, overdue: int, blocked: int, days_to_deadline: int | None) -> str:
    if blocked > 0 or overdue >= 2:
        return "high"
    if overdue == 1 or (days_to_deadline is not None and days_to_deadline <= 3):
        return "medium"
    return "normal"


def _summary_text(
    *,
    title: str,
    attention_level: str,
    overdue: int,
    blocked: int,
    due_soon: int,
    progress: int,
) -> str:
    if attention_level == "high":
        lead = f"{title} needs attention."
    elif attention_level == "medium":
        lead = f"{title} has near-term items to review."
    else:
        lead = f"{title} does not currently show a major task-state warning."
    return (
        f"{lead} Task progress is {progress}%. "
        f"There are {overdue} overdue, {blocked} blocked and {due_soon} due-soon tasks."
    )


def review_project_context(
    *,
    context: IntelligenceContextPacket,
    today: date | None = None,
) -> ProjectReviewResult:
    """Build the deterministic project review from an already-authorized context packet.

    Ask LifeOS uses this path so the reviewed tool plan is executed only once.
    The standalone review API/CLI still gathers its own context through
    ``review_owned_project``.
    """

    if context.scope_type != "project":
        raise ValueError("Project review requires project-scoped LifeOS context.")

    effective_today = today or date.today()
    execution_results = context.tool_data
    project_state = execution_results["project_state"]
    project = project_state.get("project") or {}
    tasks_result = execution_results.get("tasks") or {}
    tasks = list(tasks_result.get("tasks") or [])
    documents_result = execution_results.get("documents") or {}
    documents = list(documents_result.get("documents") or [])

    overdue_count = int(project_state.get("overdue_tasks") or 0)
    blocked_count = int(project_state.get("blocked_tasks") or 0)
    due_soon_count = int(project_state.get("due_soon_tasks") or 0)
    progress = int(project_state.get("task_progress") or 0)
    days_to_deadline = project_state.get("days_to_deadline")
    level = _attention_level(
        overdue=overdue_count,
        blocked=blocked_count,
        days_to_deadline=days_to_deadline,
    )

    signals: list[ReviewSignal] = []
    suggestions: list[ReviewSignal] = []

    attention_tasks = _select_attention_tasks(tasks, today=effective_today)
    for task in attention_tasks:
        raw_deadline = task.get("deadline")
        deadline_value: date | None = None
        if raw_deadline:
            try:
                deadline_value = date.fromisoformat(str(raw_deadline)[:10])
            except ValueError:
                deadline_value = None

        if task.get("status") == "Blocked":
            signals.append(
                ReviewSignal(
                    kind="verified_fact",
                    severity="high",
                    title=f'Blocked task: {task.get("title")}',
                    detail="This task is explicitly marked Blocked in LifeOS.",
                    evidence=_task_evidence(task),
                )
            )
        elif deadline_value and deadline_value < effective_today:
            signals.append(
                ReviewSignal(
                    kind="calculated_fact",
                    severity="high",
                    title=f'Overdue task: {task.get("title")}',
                    detail=f"Deadline was {deadline_value.isoformat()} and the task is not completed.",
                    evidence=_task_evidence(task),
                )
            )
        elif deadline_value and (deadline_value - effective_today).days <= 7:
            signals.append(
                ReviewSignal(
                    kind="calculated_fact",
                    severity="medium",
                    title=f'Due soon: {task.get("title")}',
                    detail=f"Deadline is {deadline_value.isoformat()}.",
                    evidence=_task_evidence(task),
                )
            )

    stale_documents = [
        item for item in documents if item.get("analysis_status") == "Stale"
    ]
    unanalysed_documents = [
        item for item in documents if item.get("analysis_status") == "Not analysed"
    ]

    for item in stale_documents[:3]:
        signals.append(
            ReviewSignal(
                kind="verified_fact",
                severity="medium",
                title=f'Stale document intelligence: {item.get("filename")}',
                detail=(
                    "A saved analysis exists but no longer matches the document's current text; "
                    "LifeOS is not treating those findings as current trusted context."
                ),
                evidence=_document_evidence(item),
            )
        )

    if blocked_count:
        suggestions.append(
            ReviewSignal(
                kind="suggestion",
                severity="high",
                title="Resolve a blocker before adding more work",
                detail="Review the blocked task(s) and decide the dependency or next concrete action.",
                evidence=(
                    ContextEvidence(
                        source_type="tasks",
                        source_id=None,
                        label="Blocked project tasks",
                        field="status",
                    ),
                ),
            )
        )
    elif overdue_count:
        suggestions.append(
            ReviewSignal(
                kind="suggestion",
                severity="high",
                title="Triage overdue work",
                detail="Choose whether each overdue task should be completed, rescheduled or removed.",
                evidence=(
                    ContextEvidence(
                        source_type="tasks",
                        source_id=None,
                        label="Overdue project tasks",
                        field="deadline/status",
                    ),
                ),
            )
        )
    elif due_soon_count:
        suggestions.append(
            ReviewSignal(
                kind="suggestion",
                severity="medium",
                title="Protect the next deadline",
                detail="Prioritize the highest-impact task due in the next seven days.",
                evidence=(
                    ContextEvidence(
                        source_type="tasks",
                        source_id=None,
                        label="Due-soon project tasks",
                        field="deadline",
                    ),
                ),
            )
        )

    if stale_documents:
        suggestions.append(
            ReviewSignal(
                kind="suggestion",
                severity="medium",
                title="Refresh stale document analysis before relying on it",
                detail="Re-run analysis only for the changed document(s) when their findings matter to a decision.",
                evidence=tuple(_document_evidence(item)[0] for item in stale_documents[:3]),
            )
        )
    elif unanalysed_documents:
        suggestions.append(
            ReviewSignal(
                kind="suggestion",
                severity="low",
                title="Analyse important unanalysed documents when needed",
                detail="These documents are searchable, but structured project findings are not available yet.",
                evidence=tuple(_document_evidence(item)[0] for item in unanalysed_documents[:3]),
            )
        )

    counts = documents_result.get("context_counts") or {}
    task_counts = tasks_result.get("context_counts") or {}
    context_limited = bool(
        counts.get("documents_limited")
        or task_counts.get("tasks_limited")
    )

    return ProjectReviewResult(
        project=project,
        attention_level=level,
        summary=_summary_text(
            title=str(project.get("title") or "This project"),
            attention_level=level,
            overdue=overdue_count,
            blocked=blocked_count,
            due_soon=due_soon_count,
            progress=progress,
        ),
        facts=tuple(fact.to_dict() for fact in context.facts),
        signals=tuple(signals[:8]),
        suggestions=tuple(suggestions[:5]),
        context_limited=context_limited,
    )

def review_owned_project(
    *,
    project_id: int,
    owner_id: int,
    today: date | None = None,
    registry: IntelligenceToolRegistry | None = None,
) -> ProjectReviewResult:
    """Gather owned project state once and build the deterministic review."""

    active_registry = registry or DEFAULT_INTELLIGENCE_TOOL_REGISTRY
    plan = plan_project_review(project_id=project_id, registry=active_registry)
    execution = execute_intelligence_plan(
        plan=plan,
        owner_id=owner_id,
        registry=active_registry,
    )
    context = build_project_context_packet(
        execution=execution,
        owner_id=owner_id,
    )
    return review_project_context(context=context, today=today)


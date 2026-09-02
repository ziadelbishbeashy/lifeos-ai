"""Structured, auditable context packets for LifeOS Intelligence workflows.

I2 expands the first project-only context into a reusable trusted packet.  The
packet deliberately separates exact/derived state from later LLM reasoning and
keeps provenance, freshness and context-limit metadata alongside every fact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from services.intelligence_executor_service import IntelligenceExecution


CONTEXT_SCHEMA_VERSION = "lifeos-intelligence-context-v2"
MAX_RECENT_ACTIVITY_ITEMS = 12


@dataclass(frozen=True)
class ContextEvidence:
    source_type: str
    source_id: int | None
    label: str
    field: str | None = None
    freshness: str = "current"


@dataclass(frozen=True)
class ContextFact:
    key: str
    value: Any
    fact_type: str
    confidence: str
    evidence: tuple[ContextEvidence, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "fact_type": self.fact_type,
            "confidence": self.confidence,
            "evidence": [asdict(item) for item in self.evidence],
        }


@dataclass(frozen=True)
class IntelligenceContextPacket:
    schema_version: str
    scope_type: str
    scope_id: int
    scope_label: str
    owner_id: int
    generated_at: str
    facts: tuple[ContextFact, ...]
    recent_activity: tuple[dict[str, Any], ...]
    context_limited: bool
    tool_data: dict[str, dict[str, Any]]

    def to_dict(self, *, include_tool_data: bool = False) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "scope": {
                "type": self.scope_type,
                "id": self.scope_id,
                "label": self.scope_label,
            },
            "generated_at": self.generated_at,
            "facts": [fact.to_dict() for fact in self.facts],
            "recent_activity": list(self.recent_activity),
            "context_limited": self.context_limited,
        }
        if include_tool_data:
            payload["tool_data"] = self.tool_data
        return payload


def _project_evidence(project_id: int, field: str) -> tuple[ContextEvidence, ...]:
    return (
        ContextEvidence(
            source_type="project",
            source_id=project_id,
            label="Project state",
            field=field,
        ),
    )


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _activity_item(
    *,
    source_type: str,
    source_id: int | None,
    label: str,
    event: str,
    occurred_at: Any,
    freshness: str = "current",
) -> tuple[datetime, dict[str, Any]] | None:
    timestamp = _parse_datetime(occurred_at)
    if timestamp is None:
        return None
    return (
        timestamp,
        {
            "source_type": source_type,
            "source_id": source_id,
            "label": str(label or source_type).strip() or source_type,
            "event": event,
            "occurred_at": timestamp.isoformat(),
            "freshness": freshness,
        },
    )


def _build_recent_project_activity(
    execution: IntelligenceExecution,
) -> tuple[dict[str, Any], ...]:
    """Derive bounded activity only from already-authorized tool results."""

    entries: list[tuple[datetime, dict[str, Any]]] = []
    project_state = execution.results.get("project_state") or {}
    project = project_state.get("project") or {}

    project_activity = _activity_item(
        source_type="project",
        source_id=project.get("id"),
        label=project.get("title") or "Project",
        event="project_updated",
        occurred_at=project.get("updated_at"),
    )
    if project_activity:
        entries.append(project_activity)

    tasks = (execution.results.get("tasks") or {}).get("tasks") or []
    for task in tasks:
        completed = _activity_item(
            source_type="task",
            source_id=task.get("id"),
            label=task.get("title") or "Task",
            event="task_completed",
            occurred_at=task.get("completed_at"),
        )
        if completed:
            entries.append(completed)
            continue
        created = _activity_item(
            source_type="task",
            source_id=task.get("id"),
            label=task.get("title") or "Task",
            event="task_created",
            occurred_at=task.get("created_at"),
        )
        if created:
            entries.append(created)

    documents = (execution.results.get("documents") or {}).get("documents") or []
    for document in documents:
        activity = _activity_item(
            source_type="document",
            source_id=document.get("id"),
            label=document.get("filename") or "Document",
            event="document_uploaded",
            occurred_at=document.get("uploaded_at"),
            freshness=(
                "current"
                if document.get("analysis_status") == "Current"
                else "stale_or_unanalysed"
            ),
        )
        if activity:
            entries.append(activity)

    notes = (execution.results.get("notes") or {}).get("notes") or []
    for note in notes:
        activity = _activity_item(
            source_type="note",
            source_id=note.get("id"),
            label=note.get("title") or "Note",
            event="note_updated",
            occurred_at=note.get("updated_at"),
        )
        if activity:
            entries.append(activity)

    entries.sort(key=lambda item: item[0], reverse=True)
    return tuple(item for _, item in entries[:MAX_RECENT_ACTIVITY_ITEMS])


def build_project_context_packet(
    *,
    execution: IntelligenceExecution,
    owner_id: int,
) -> IntelligenceContextPacket:
    """Convert safe-tool results into typed factual project context."""

    summary = execution.results.get("project_state") or {}
    project = summary.get("project") or {}
    project_id = int(project.get("id") or execution.plan.scope_id)
    project_title = str(project.get("title") or f"Project {project_id}").strip()

    tasks_result = execution.results.get("tasks") or {}
    documents_result = execution.results.get("documents") or {}
    notes_result = execution.results.get("notes") or {}
    document_counts = documents_result.get("context_counts") or {}
    task_counts = tasks_result.get("context_counts") or {}
    documents = list(documents_result.get("documents") or [])

    stale_count = int(document_counts.get("documents_with_stale_analysis") or 0)
    unanalysed_count = int(document_counts.get("documents_without_analysis") or 0)
    if not document_counts:
        stale_count = sum(1 for item in documents if item.get("analysis_status") == "Stale")
        unanalysed_count = sum(
            1 for item in documents if item.get("analysis_status") == "Not analysed"
        )

    facts = (
        ContextFact(
            key="project.title",
            value=project_title,
            fact_type="verified",
            confidence="high",
            evidence=_project_evidence(project_id, "title"),
        ),
        ContextFact(
            key="project.status",
            value=project.get("status") or "",
            fact_type="verified",
            confidence="high",
            evidence=_project_evidence(project_id, "status"),
        ),
        ContextFact(
            key="project.priority",
            value=project.get("priority") or "",
            fact_type="verified",
            confidence="high",
            evidence=_project_evidence(project_id, "priority"),
        ),
        ContextFact(
            key="project.current_phase",
            value=project.get("current_phase") or "",
            fact_type="verified",
            confidence="high",
            evidence=_project_evidence(project_id, "current_phase"),
        ),
        ContextFact(
            key="project.deadline",
            value=project.get("deadline"),
            fact_type="verified",
            confidence="high",
            evidence=_project_evidence(project_id, "deadline"),
        ),
        ContextFact(
            key="project.manual_progress",
            value=int(project.get("progress") or 0),
            fact_type="verified",
            confidence="high",
            evidence=_project_evidence(project_id, "progress"),
        ),
        ContextFact(
            key="project.task_progress",
            value=int(summary.get("task_progress") or 0),
            fact_type="calculated",
            confidence="high",
            evidence=(
                ContextEvidence(
                    source_type="tasks",
                    source_id=None,
                    label="Owned project tasks",
                    field="completion ratio",
                ),
            ),
        ),
        ContextFact(
            key="project.total_tasks",
            value=int(summary.get("total_tasks") or 0),
            fact_type="calculated",
            confidence="high",
            evidence=(ContextEvidence("tasks", None, "Owned project tasks", "count"),),
        ),
        ContextFact(
            key="project.completed_tasks",
            value=int(summary.get("completed_tasks") or 0),
            fact_type="calculated",
            confidence="high",
            evidence=(ContextEvidence("tasks", None, "Owned project tasks", "status"),),
        ),
        ContextFact(
            key="project.overdue_tasks",
            value=int(summary.get("overdue_tasks") or 0),
            fact_type="calculated",
            confidence="high",
            evidence=(
                ContextEvidence("tasks", None, "Owned project tasks", "deadline/status"),
            ),
        ),
        ContextFact(
            key="project.blocked_tasks",
            value=int(summary.get("blocked_tasks") or 0),
            fact_type="calculated",
            confidence="high",
            evidence=(ContextEvidence("tasks", None, "Owned project tasks", "status"),),
        ),
        ContextFact(
            key="project.due_soon_tasks",
            value=int(summary.get("due_soon_tasks") or 0),
            fact_type="calculated",
            confidence="high",
            evidence=(ContextEvidence("tasks", None, "Owned project tasks", "deadline"),),
        ),
        ContextFact(
            key="project.current_documents",
            value=int(summary.get("current_document_count") or 0),
            fact_type="calculated",
            confidence="high",
            evidence=(
                ContextEvidence(
                    source_type="documents",
                    source_id=None,
                    label="Current owned project documents",
                    field="version status",
                ),
            ),
        ),
        ContextFact(
            key="project.stale_document_analyses",
            value=stale_count,
            fact_type="calculated",
            confidence="high",
            evidence=(
                ContextEvidence(
                    "documents", None, "Owned project documents", "analysis_status"
                ),
            ),
        ),
        ContextFact(
            key="project.unanalysed_documents",
            value=unanalysed_count,
            fact_type="calculated",
            confidence="high",
            evidence=(
                ContextEvidence(
                    "documents", None, "Owned project documents", "analysis_status"
                ),
            ),
        ),
        ContextFact(
            key="project.notes_count",
            value=int(summary.get("notes_count") or notes_result.get("count") or 0),
            fact_type="calculated",
            confidence="high",
            evidence=(ContextEvidence("notes", None, "Owned project notes", "count"),),
        ),
    )

    context_limited = bool(
        document_counts.get("documents_limited")
        or task_counts.get("tasks_limited")
        or task_counts.get("context_limited")
    )

    return IntelligenceContextPacket(
        schema_version=CONTEXT_SCHEMA_VERSION,
        scope_type="project",
        scope_id=project_id,
        scope_label=project_title,
        owner_id=int(owner_id),
        generated_at=datetime.now(timezone.utc).isoformat(),
        facts=facts,
        recent_activity=_build_recent_project_activity(execution),
        context_limited=context_limited,
        tool_data=execution.results,
    )


def collect_owned_project_context(
    *,
    project_id: int,
    owner_id: int,
):
    """Run the reviewed read-only project plan and return its trusted context packet."""

    # Local imports avoid turning the context data types into orchestration
    # dependencies for callers that only need to deserialize/format facts.
    from services.intelligence_executor_service import execute_intelligence_plan
    from services.intelligence_planner_service import plan_project_review

    plan = plan_project_review(project_id=int(project_id))
    execution = execute_intelligence_plan(plan=plan, owner_id=int(owner_id))
    packet = build_project_context_packet(execution=execution, owner_id=int(owner_id))

    # I16 adds only explicit, structured memory as additional trusted facts.
    # Raw chat history and document prose are never inserted as memory.
    from services.structured_memory_service import memory_context_rows

    memory_facts = tuple(
        ContextFact(
            key=row["key"],
            value=row["value"],
            fact_type=row["fact_type"],
            confidence="high" if row["fact_type"] == "user_confirmed" else "medium",
            evidence=(
                ContextEvidence(
                    source_type="memory",
                    source_id=row["memory_id"],
                    label=row["label"],
                    field="structured memory",
                    freshness="current",
                ),
            ),
        )
        for row in memory_context_rows(
            owner_id=int(owner_id),
            project_id=int(project_id),
        )
    )
    # Experience profile is also explicit user-controlled preference context.
    # It may shape terminology/recommendations, but it never substitutes for
    # workspace evidence such as deadlines, tasks, grades or project state.
    from services.experience_profile_service import experience_context_for_ai

    experience = experience_context_for_ai(int(owner_id))
    experience_facts: tuple[ContextFact, ...] = ()
    if experience.get("is_configured") and experience.get("primary_experience"):
        experience_facts = (
            ContextFact(
                key="user.experience.primary",
                value={
                    "key": experience.get("primary_experience"),
                    "label": experience.get("label"),
                    "enabled": experience.get("enabled_experiences") or [],
                },
                fact_type="user_preference",
                confidence="high",
                evidence=(
                    ContextEvidence(
                        source_type="experience_profile",
                        source_id=int(owner_id),
                        label="User-selected LifeOS experience",
                        field="primary experience",
                        freshness="current",
                    ),
                ),
            ),
        )

    extra_facts = memory_facts + experience_facts
    if not extra_facts:
        return packet
    return IntelligenceContextPacket(
        schema_version=packet.schema_version,
        scope_type=packet.scope_type,
        scope_id=packet.scope_id,
        scope_label=packet.scope_label,
        owner_id=packet.owner_id,
        generated_at=packet.generated_at,
        facts=packet.facts + extra_facts,
        recent_activity=packet.recent_activity,
        context_limited=packet.context_limited,
        tool_data=packet.tool_data,
    )

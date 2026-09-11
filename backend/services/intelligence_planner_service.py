"""Deterministic planning for the first LifeOS Intelligence vertical slice.

This first planner intentionally does not ask an LLM which tools exist. Plans are
reviewed code and can only reference tools from the allow-list. Later natural
language routing can choose among these reviewed plans without gaining direct DB
or arbitrary-tool access.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from services.intelligence_tool_registry_service import (
    DEFAULT_INTELLIGENCE_TOOL_REGISTRY,
    IntelligenceToolRegistry,
)


@dataclass(frozen=True)
class IntelligencePlanStep:
    step_id: str
    tool_name: str
    arguments: dict[str, Any]
    purpose: str


@dataclass(frozen=True)
class IntelligencePlan:
    intent: str
    scope_type: str
    scope_id: int
    steps: tuple[IntelligencePlanStep, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "steps": [asdict(step) for step in self.steps],
        }


def plan_project_review(
    *,
    project_id: int,
    registry: IntelligenceToolRegistry | None = None,
) -> IntelligencePlan:
    """Plan the read-only data collection required for a project review."""

    active_registry = registry or DEFAULT_INTELLIGENCE_TOOL_REGISTRY
    tool_names = (
        "project.get_summary",
        "project.get_tasks",
        "project.get_documents",
        "project.get_recent_notes",
    )
    # Fail during planning if a deployment accidentally removed a required tool.
    for name in tool_names:
        spec = active_registry.get(name)
        if spec.mutates_state:
            raise RuntimeError(
                "Project review plans may only contain read-only intelligence tools."
            )

    return IntelligencePlan(
        intent="project_review",
        scope_type="project",
        scope_id=int(project_id),
        steps=(
            IntelligencePlanStep(
                step_id="project_state",
                tool_name="project.get_summary",
                arguments={"project_id": int(project_id)},
                purpose="Establish exact project state, deadline and deterministic health.",
            ),
            IntelligencePlanStep(
                step_id="tasks",
                tool_name="project.get_tasks",
                arguments={"project_id": int(project_id)},
                purpose="Identify blocked, overdue and upcoming work.",
            ),
            IntelligencePlanStep(
                step_id="documents",
                tool_name="project.get_documents",
                arguments={"project_id": int(project_id)},
                purpose="Inspect current/stale document intelligence and trusted findings.",
            ),
            IntelligencePlanStep(
                step_id="notes",
                tool_name="project.get_recent_notes",
                arguments={"project_id": int(project_id)},
                purpose="Include recent user-owned project context without changing it.",
            ),
        ),
    )

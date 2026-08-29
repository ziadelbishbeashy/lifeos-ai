"""Safe executor for reviewed LifeOS intelligence plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.intelligence_planner_service import IntelligencePlan
from services.intelligence_tool_registry_service import (
    DEFAULT_INTELLIGENCE_TOOL_REGISTRY,
    IntelligenceToolRegistry,
)


@dataclass(frozen=True)
class IntelligenceExecution:
    plan: IntelligencePlan
    results: dict[str, dict[str, Any]]


def execute_intelligence_plan(
    *,
    plan: IntelligencePlan,
    owner_id: int,
    registry: IntelligenceToolRegistry | None = None,
) -> IntelligenceExecution:
    """Execute one reviewed plan with mutations disabled by default."""

    active_registry = registry or DEFAULT_INTELLIGENCE_TOOL_REGISTRY
    results: dict[str, dict[str, Any]] = {}

    for step in plan.steps:
        result = active_registry.execute(
            step.tool_name,
            owner_id=owner_id,
            arguments=step.arguments,
            allow_mutation=False,
        )
        results[step.step_id] = result.data

    return IntelligenceExecution(plan=plan, results=results)

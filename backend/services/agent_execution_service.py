"""Safe I19 orchestration dispatcher.

LangGraph is opt-in. The established I19 runtime remains the default and the
fallback when the optional dependency is unavailable. Runtime failures after a
graph has started are *not* retried through legacy execution, preventing duplicate
tool/provider work and duplicate cost.
"""
from __future__ import annotations

import os
from typing import Any

from services.agent_runtime_service import run_owned_agent_goal as run_owned_agent_goal_legacy
from services.intelligence_tool_registry_service import IntelligenceToolRegistry
from services.langsmith_observability_service import trace_lifeos_span


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def langgraph_i19_enabled() -> bool:
    return _bool_env("AI_LANGGRAPH_I19_ENABLED", False)


def agent_orchestration_status() -> dict[str, Any]:
    available = False
    try:
        from services.agent_langgraph_runtime_service import langgraph_available
        available = bool(langgraph_available())
    except Exception:
        available = False
    return {
        "langgraph_enabled": langgraph_i19_enabled(),
        "langgraph_available": available,
        "active_runtime": "langgraph" if langgraph_i19_enabled() and available else "legacy_i19",
        "fallback_policy": "unavailable_only",
        "graph_checkpointing": False,
        "workspace_mutation": False,
        "confirmation_boundary": "I9",
    }


@trace_lifeos_span(
    name="LifeOS I19 goal execution",
    feature="agent_goal_execution",
    metadata_builder=lambda values: {
        "goal_characters": len(str(values.get("goal") or "")),
        "selected_context_type": (
            str((values.get("selected_context") or {}).get("type") or "none")
            if isinstance(values.get("selected_context"), dict)
            else "none"
        ),
        "orchestrator_requested": "langgraph" if langgraph_i19_enabled() else "legacy_i19",
    },
    output_metadata_builder=lambda run: {
        "status": getattr(run, "status", "unknown"),
        "tool_calls": int(getattr(run, "tool_calls", 0) or 0),
        "provider_calls": int(getattr(run, "provider_calls", 0) or 0),
        "orchestration": (
            (getattr(run, "output", {}) or {}).get("orchestration", "legacy_i19")
            if run is not None
            else "unknown"
        ),
    },
)
def run_owned_agent_goal(
    *,
    owner_id: int,
    goal: Any,
    selected_context: Any = None,
    registry: IntelligenceToolRegistry | None = None,
):
    """Dispatch one I19 goal without weakening any LifeOS safety boundary."""
    if not langgraph_i19_enabled():
        return run_owned_agent_goal_legacy(
            owner_id=owner_id,
            goal=goal,
            selected_context=selected_context,
            registry=registry,
        )

    try:
        from services.agent_langgraph_runtime_service import (
            LangGraphUnavailableError,
            run_owned_agent_goal_langgraph,
        )
    except Exception:
        # Import/setup failure before any graph work: safe to use established I19.
        return run_owned_agent_goal_legacy(
            owner_id=owner_id,
            goal=goal,
            selected_context=selected_context,
            registry=registry,
        )

    try:
        return run_owned_agent_goal_langgraph(
            owner_id=owner_id,
            goal=goal,
            selected_context=selected_context,
            registry=registry,
        )
    except LangGraphUnavailableError:
        # Only dependency/unavailability failures fall back. We intentionally do
        # not rerun a graph that failed after execution began, avoiding duplicate
        # reads/provider calls and preserving the original audit trail.
        return run_owned_agent_goal_legacy(
            owner_id=owner_id,
            goal=goal,
            selected_context=selected_context,
            registry=registry,
        )

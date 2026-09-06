"""Optional LangGraph orchestration for the existing constrained I19 runtime.

This module intentionally does *not* turn LifeOS into a generic autonomous agent.
The graph only orchestrates the deterministic I19 plan that already exists:

    deterministic planner -> reviewed read-only tools -> bounded evidence
    -> existing LifeOS reasoner -> existing audited LifeOSAgentRun

Important safety boundaries remain outside the graph:
- The model never chooses tool names or resource IDs.
- Every tool comes from the reviewed LifeOS registry and is invoked read-only.
- The graph has no ORM/SQL/filesystem/URL/model-write tool.
- Workspace mutation remains a separate LifeOSActionProposal + I9 confirmation.
- No LangGraph checkpointer is used in this first rollout; LifeOS's existing
  LifeOSAgentRun remains the authoritative audit record.
- Graph state contains metadata/counts only. User goals, evidence, tool results,
  prompts, and answers stay in LifeOS-owned runtime memory/audit storage so
  automatic LangSmith graph tracing does not copy raw user content.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import time
from typing import Any, TypedDict

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import LifeOSAgentRun
from services.agent_planner_service import AgentPlan, AgentPlannerError, plan_owned_agent_goal
from services.agent_reasoning_service import AgentReasoningError, reason_over_agent_observations
from services.ask_context_picker_service import AskContextNotFoundError, AskContextValidationError
from services.agent_runtime_service import (
    AGENT_LIMITS,
    AgentLimitError,
    AgentRuntimeError,
    _action_suggestions,
    _build_evidence_catalog,
    _clean,
    _compact_tool_result,
    _goal_summary,
    _json_safe,
    _knowledge_result_is_direct,
    _save_run,
    _trusted_fallback_answer,
)
from services.intelligence_tool_registry_service import (
    DEFAULT_INTELLIGENCE_TOOL_REGISTRY,
    IntelligenceToolRegistry,
)

try:  # Optional dependency: legacy I19 remains available if installation fails.
    from langgraph.graph import END, START, StateGraph
except Exception:  # pragma: no cover - exercised by dispatcher fallback tests
    END = START = StateGraph = None  # type: ignore[assignment]


class LangGraphUnavailableError(AgentRuntimeError):
    """Raised only when the optional LangGraph runtime cannot be initialized."""


class _SafeGraphState(TypedDict, total=False):
    """Only non-sensitive orchestration metadata may enter LangGraph state."""

    phase: str
    run_id: int | None
    scope_type: str
    scope_id: int | None
    step_index: int
    step_count: int
    current_tool: str | None
    tool_calls: int
    provider_calls: int
    failed: bool
    failure_code: str | None


@dataclass
class _RuntimeContext:
    """Sensitive/domain state kept outside LangGraph's traced state object."""

    owner_id: int
    goal: Any
    selected_context: Any = None
    registry: IntelligenceToolRegistry | None = None
    plan: AgentPlan | None = None
    observations: dict[str, dict[str, Any]] = field(default_factory=dict)
    trace: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    reasoning: dict[str, Any] = field(default_factory=dict)
    goal_summary: dict[str, Any] = field(default_factory=dict)
    provider: str | None = None
    model: str | None = None
    run_id: int | None = None
    started_clock: float | None = None
    failure_message: str | None = None
    tool_calls: int = 0
    provider_calls: int = 0

    @property
    def active_registry(self) -> IntelligenceToolRegistry:
        return self.registry or DEFAULT_INTELLIGENCE_TOOL_REGISTRY


def langgraph_available() -> bool:
    return StateGraph is not None and START is not None and END is not None


def _require_graph() -> None:
    if not langgraph_available():
        raise LangGraphUnavailableError(
            "LangGraph is not installed. LifeOS can continue with the existing I19 runtime."
        )


def _runtime_elapsed(context: _RuntimeContext) -> float:
    if context.started_clock is None:
        return 0.0
    return time.monotonic() - context.started_clock


def _plan_node(context: _RuntimeContext, state: _SafeGraphState) -> _SafeGraphState:
    plan = plan_owned_agent_goal(
        owner_id=int(context.owner_id),
        goal=context.goal,
        selected_context=context.selected_context,
        registry=context.registry,
    )
    if len(plan.steps) > AGENT_LIMITS["max_steps"]:
        raise AgentLimitError("The agent plan exceeded the maximum step limit.")
    context.plan = plan
    return {
        "phase": "planned",
        "scope_type": plan.scope.type,
        "scope_id": plan.scope.id,
        "step_index": 0,
        "step_count": len(plan.steps),
        "current_tool": None,
        "tool_calls": 0,
        "provider_calls": 0,
        "failed": False,
        "failure_code": None,
    }


def _start_audit_node(context: _RuntimeContext, state: _SafeGraphState) -> _SafeGraphState:
    plan = context.plan
    if plan is None:
        raise AgentRuntimeError("LifeOS could not start the graph without a validated plan.")

    run = LifeOSAgentRun(
        user_id=int(context.owner_id),
        goal=plan.goal,
        scope_type=plan.scope.type,
        scope_id=plan.scope.id,
        scope_label=plan.scope.label,
        status="running",
        plan_json=json.dumps(plan.to_dict(), ensure_ascii=False),
        trace_json="[]",
        output_json="{}",
        limits_json=json.dumps(AGENT_LIMITS, ensure_ascii=False),
        started_at=datetime.utcnow(),
    )
    try:
        db.session.add(run)
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise AgentRuntimeError("LifeOS could not start the agent run.") from error

    context.run_id = int(run.id)
    context.started_clock = time.monotonic()
    return {"phase": "running", "run_id": int(run.id)}


def _execute_tool_node(context: _RuntimeContext, state: _SafeGraphState) -> _SafeGraphState:
    plan = context.plan
    if plan is None:
        raise AgentRuntimeError("The validated I19 plan is unavailable.")

    index = int(state.get("step_index") or 0)
    tool_calls = int(state.get("tool_calls") or 0)
    provider_calls = int(state.get("provider_calls") or 0)

    if index >= len(plan.steps):
        return {"phase": "tools_complete", "current_tool": None}
    if tool_calls >= AGENT_LIMITS["max_tool_calls"]:
        context.failure_message = "The agent reached its tool-call limit."
        return {"phase": "failed", "failed": True, "failure_code": "tool_limit"}
    if _runtime_elapsed(context) > AGENT_LIMITS["max_runtime_seconds"]:
        context.failure_message = "The agent reached its runtime limit."
        return {"phase": "failed", "failed": True, "failure_code": "runtime_limit"}

    step = plan.steps[index]
    step_started = time.monotonic()
    try:
        # The existing registry performs contract/ownership checks. The graph
        # hard-codes allow_mutation=False and never accepts model-selected tools.
        result = context.active_registry.execute(
            step.tool_name,
            owner_id=int(context.owner_id),
            arguments=step.arguments,
            allow_mutation=False,
        )
        tool_calls += 1
        context.tool_calls = tool_calls
        if step.tool_name == "knowledge.ask_context":
            # Preserve the conservative budget accounting of the legacy runtime.
            provider_calls += 2
            context.provider_calls = provider_calls
        context.observations[step.step_id] = result.data
        context.trace.append({
            "index": index + 1,
            "step_id": step.step_id,
            "tool_name": step.tool_name,
            "purpose": step.purpose,
            "status": "succeeded",
            "duration_ms": round((time.monotonic() - step_started) * 1000, 2),
            "result": _compact_tool_result(step.tool_name, result.data),
        })
        return {
            "phase": "tool_succeeded",
            "step_index": index + 1,
            "current_tool": step.tool_name,
            "tool_calls": tool_calls,
            "provider_calls": provider_calls,
        }
    except Exception as error:
        # Same product behavior as the legacy runtime: preserve a user-safe audit
        # record. No workspace mutation can have occurred because tools are read-only.
        context.trace.append({
            "index": index + 1,
            "step_id": step.step_id,
            "tool_name": step.tool_name,
            "purpose": step.purpose,
            "status": "failed",
            "duration_ms": round((time.monotonic() - step_started) * 1000, 2),
            "error": _clean(error, 1200),
        })
        context.failure_message = _clean(error, 1600) or "The agent tool step failed."
        return {
            "phase": "failed",
            "step_index": index + 1,
            "current_tool": step.tool_name,
            "tool_calls": tool_calls,
            "provider_calls": provider_calls,
            "failed": True,
            "failure_code": "tool_failed",
        }


def _after_tool(context: _RuntimeContext, state: _SafeGraphState) -> str:
    if bool(state.get("failed")):
        return "finalize"
    plan = context.plan
    if plan is None:
        return "finalize"
    if int(state.get("step_index") or 0) < len(plan.steps):
        return "execute_tool"
    return "reason"


def _reason_node(context: _RuntimeContext, state: _SafeGraphState) -> _SafeGraphState:
    plan = context.plan
    if plan is None:
        context.failure_message = "The validated I19 plan is unavailable before reasoning."
        return {"phase": "failed", "failed": True, "failure_code": "missing_plan"}

    provider_calls = int(state.get("provider_calls") or 0)
    context.evidence = _build_evidence_catalog(plan=plan, observations=context.observations)
    context.suggestions = _action_suggestions(context.observations)[:2]

    if _runtime_elapsed(context) > AGENT_LIMITS["max_runtime_seconds"]:
        context.failure_message = "The agent reached its runtime limit before final reasoning."
        return {"phase": "failed", "failed": True, "failure_code": "runtime_limit"}

    if _knowledge_result_is_direct(plan):
        context.reasoning = _trusted_fallback_answer(
            plan=plan,
            observations=context.observations,
            evidence=context.evidence,
        )
        context.provider = None
        context.model = None
    else:
        if provider_calls >= AGENT_LIMITS["max_provider_calls"]:
            context.failure_message = "The agent reached its AI-call limit before final reasoning."
            return {"phase": "failed", "failed": True, "failure_code": "provider_limit"}
        provider_calls += 1
        context.provider_calls = provider_calls
        try:
            reasoned = reason_over_agent_observations(
                goal=plan.goal,
                scope=plan.scope.to_dict(),
                evidence_catalog=context.evidence,
            )
            context.reasoning = {
                **reasoned.to_dict(),
                "verification_status": "verified_evidence_ids",
                "reasoning_mode": "provider_reasoning",
            }
            context.provider = reasoned.provider
            context.model = reasoned.model
            if _runtime_elapsed(context) > AGENT_LIMITS["max_runtime_seconds"]:
                context.failure_message = "The agent reached its runtime limit during final reasoning."
                return {
                    "phase": "failed",
                    "provider_calls": provider_calls,
                    "failed": True,
                    "failure_code": "runtime_limit",
                }
        except AgentReasoningError as error:
            context.reasoning = _trusted_fallback_answer(
                plan=plan,
                observations=context.observations,
                evidence=context.evidence,
            )
            context.reasoning["provider_failure"] = _clean(error, 1000)
            context.provider = None
            context.model = None
        except Exception as error:
            # Preserve the legacy runtime's broad safety boundary without
            # exposing an unexpected internal exception to automatic graph traces.
            context.failure_message = _clean(error, 1600) or "The agent reasoning step failed."
            return {
                "phase": "failed",
                "provider_calls": provider_calls,
                "failed": True,
                "failure_code": "reasoning_failed",
            }

    context.goal_summary = _goal_summary(
        plan=plan,
        evidence=context.evidence,
        reasoning=context.reasoning,
        suggestions=context.suggestions,
    )
    return {
        "phase": "reasoned",
        "provider_calls": provider_calls,
        "failed": False,
        "failure_code": None,
    }


def _finalize_node(context: _RuntimeContext, state: _SafeGraphState) -> _SafeGraphState:
    if context.run_id is None or context.plan is None:
        raise AgentRuntimeError("LifeOS could not finalize an agent run that was not started.")

    run = LifeOSAgentRun.query.filter_by(
        id=int(context.run_id), user_id=int(context.owner_id)
    ).first()
    if run is None:
        raise AgentRuntimeError("LifeOS could not reload the owned agent audit record.")

    tool_calls = int(state.get("tool_calls") or 0)
    provider_calls = int(state.get("provider_calls") or 0)
    failed = bool(state.get("failed"))

    if failed:
        run.status = "failed"
        run.trace_json = json.dumps(_json_safe(context.trace), ensure_ascii=False)
        run.output_json = json.dumps({
            "answer": None,
            "evidence": _build_evidence_catalog(
                plan=context.plan, observations=context.observations
            ),
            "action_suggestions": [],
            "prepared_proposals": [],
            "read_only": True,
            "workspace_mutation": False,
            "confirmation_boundary": "I9",
            "orchestration": "langgraph",
        }, ensure_ascii=False)
        run.failure_message = context.failure_message or "The agent run failed."
    else:
        reasoning = context.reasoning
        run.status = "succeeded"
        run.trace_json = json.dumps(_json_safe(context.trace), ensure_ascii=False)
        run.output_json = json.dumps({
            "answer": reasoning.get("answer"),
            "goal_summary": context.goal_summary,
            "claims": reasoning.get("claims") or [],
            "recommendations": reasoning.get("recommendations") or [],
            "verification_status": reasoning.get("verification_status"),
            "reasoning_mode": reasoning.get("reasoning_mode"),
            "provider_failure": reasoning.get("provider_failure"),
            "evidence": context.evidence,
            "action_suggestions": context.suggestions,
            "prepared_proposals": [],
            "read_only": True,
            "workspace_mutation": False,
            "confirmation_boundary": "I9",
            "context_limited": any(
                bool((context.observations.get(step.step_id) or {}).get("context_limited"))
                for step in context.plan.steps
            ),
            "orchestration": "langgraph",
        }, ensure_ascii=False)
        run.failure_message = None

    run.provider = context.provider
    run.model = context.model
    run.provider_calls = provider_calls
    run.tool_calls = tool_calls
    run.finished_at = datetime.utcnow()
    _save_run(run)
    return {"phase": "failed" if failed else "completed"}


def _build_graph(context: _RuntimeContext):
    _require_graph()

    # Node closures access LifeOS-owned runtime context. The StateGraph itself
    # receives/returns only _SafeGraphState metadata, keeping automatic traces
    # free of raw goals, evidence, prompts, tool results, and answers.
    builder = StateGraph(_SafeGraphState)
    builder.add_node("plan", lambda state: _plan_node(context, state))
    builder.add_node("start_audit", lambda state: _start_audit_node(context, state))
    builder.add_node("execute_tool", lambda state: _execute_tool_node(context, state))
    builder.add_node("reason", lambda state: _reason_node(context, state))
    builder.add_node("finalize", lambda state: _finalize_node(context, state))

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "start_audit")
    builder.add_edge("start_audit", "execute_tool")
    builder.add_conditional_edges(
        "execute_tool",
        lambda state: _after_tool(context, state),
        {
            "execute_tool": "execute_tool",
            "reason": "reason",
            "finalize": "finalize",
        },
    )
    builder.add_edge("reason", "finalize")
    builder.add_edge("finalize", END)

    # Deliberately no checkpointer in the first rollout. LifeOSAgentRun remains
    # the durable audit boundary and I9 remains the human-confirmation boundary.
    return builder.compile()


def _finalize_unexpected_failure(context: _RuntimeContext, error: Exception) -> LifeOSAgentRun:
    """Persist a safe failed audit after an unexpected graph/runtime exception."""
    if context.run_id is None or context.plan is None:
        raise AgentRuntimeError("LangGraph could not start the I19 review safely.") from error

    run = LifeOSAgentRun.query.filter_by(
        id=int(context.run_id), user_id=int(context.owner_id)
    ).first()
    if run is None:
        raise AgentRuntimeError("LangGraph lost the owned I19 audit record.") from error

    run.status = "failed"
    run.trace_json = json.dumps(_json_safe(context.trace), ensure_ascii=False)
    run.output_json = json.dumps({
        "answer": None,
        "evidence": _build_evidence_catalog(
            plan=context.plan, observations=context.observations
        ),
        "action_suggestions": [],
        "prepared_proposals": [],
        "read_only": True,
        "workspace_mutation": False,
        "confirmation_boundary": "I9",
        "orchestration": "langgraph",
    }, ensure_ascii=False)
    run.provider_calls = int(context.provider_calls or 0)
    run.tool_calls = int(context.tool_calls or 0)
    run.finished_at = datetime.utcnow()
    run.failure_message = _clean(error, 1600) or "The LangGraph agent run failed."
    _save_run(run)
    return run


def run_owned_agent_goal_langgraph(
    *,
    owner_id: int,
    goal: Any,
    selected_context: Any = None,
    registry: IntelligenceToolRegistry | None = None,
) -> LifeOSAgentRun:
    """Execute I19 through LangGraph without changing LifeOS domain boundaries."""
    _require_graph()
    context = _RuntimeContext(
        owner_id=int(owner_id),
        goal=goal,
        selected_context=selected_context,
        registry=registry,
    )
    graph = _build_graph(context)
    initial_state: _SafeGraphState = {
        "phase": "starting",
        "run_id": None,
        "scope_type": "pending",
        "scope_id": None,
        "step_index": 0,
        "step_count": 0,
        "current_tool": None,
        "tool_calls": 0,
        "provider_calls": 0,
        "failed": False,
        "failure_code": None,
    }
    try:
        final_state = graph.invoke(initial_state)
    except (AgentPlannerError, AskContextValidationError, AskContextNotFoundError):
        # Preserve the existing validation/not-found contract: planning failures
        # are not converted into a 503 agent-runtime failure.
        raise
    except AgentRuntimeError:
        raise
    except Exception as error:
        return _finalize_unexpected_failure(context, error)

    if context.run_id is None:
        raise AgentRuntimeError("LangGraph completed without an owned LifeOS agent audit record.")
    run = LifeOSAgentRun.query.filter_by(
        id=int(context.run_id), user_id=int(owner_id)
    ).first()
    if run is None:
        raise AgentRuntimeError("LangGraph completed but the LifeOS agent audit record was unavailable.")
    return run

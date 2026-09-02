"""I19.1 — constrained goal planning for the LifeOS Agent Runtime.

The planner turns a user goal into a small read-only plan over the reviewed I1
registry.  It never accepts arbitrary tool names, SQL, URLs, Python, or model-
supplied resource IDs.  Explicit context is ownership-validated first, then code
chooses the smallest reviewed tool set that can answer the goal.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from services.ask_context_picker_service import (
    AskContextNotFoundError,
    AskContextOption,
    AskContextValidationError,
    validate_owned_ask_context,
)
from services.intelligence_tool_registry_service import (
    DEFAULT_INTELLIGENCE_TOOL_REGISTRY,
    IntelligenceToolRegistry,
)

MAX_AGENT_GOAL_CHARACTERS = 2_000
MAX_AGENT_PLAN_STEPS = 6
KNOWLEDGE_SCOPE_TYPES = frozenset({"document", "collection", "module", "lecture"})


class AgentPlannerError(ValueError):
    pass


@dataclass(frozen=True)
class AgentScope:
    type: str
    id: int | None
    label: str
    project_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentPlanStep:
    step_id: str
    tool_name: str
    arguments: dict[str, Any]
    purpose: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentPlan:
    version: int
    goal: str
    scope: AgentScope
    planner_mode: str
    steps: tuple[AgentPlanStep, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "goal": self.goal,
            "scope": self.scope.to_dict(),
            "planner_mode": self.planner_mode,
            "steps": [step.to_dict() for step in self.steps],
            "safety": {
                "read_only_tools_only": True,
                "arbitrary_tools": False,
                "arbitrary_sql": False,
                "arbitrary_code": False,
                "workspace_mutation": False,
                "important_actions_require": "I9_confirmation",
            },
        }


def _clean_goal(value: Any) -> str:
    goal = " ".join(str(value or "").split()).strip()
    if not goal:
        raise AgentPlannerError("Tell LifeOS what goal you want help with.")
    if len(goal) > MAX_AGENT_GOAL_CHARACTERS:
        raise AgentPlannerError(
            f"Keep the agent goal under {MAX_AGENT_GOAL_CHARACTERS:,} characters."
        )
    return goal


def _scope_from_context(option: AskContextOption | None) -> AgentScope:
    if option is None:
        return AgentScope(type="workspace", id=None, label="All LifeOS")
    return AgentScope(
        type=option.type,
        id=int(option.id),
        label=str(option.label),
        project_id=int(option.project_id) if option.project_id is not None else None,
    )


def _append_step(
    steps: list[AgentPlanStep],
    *,
    registry: IntelligenceToolRegistry,
    step_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    purpose: str,
) -> None:
    spec = registry.get(tool_name)
    if spec.mutates_state:
        raise AgentPlannerError("Agent plans may only contain reviewed read-only tools.")
    steps.append(AgentPlanStep(step_id, tool_name, arguments, purpose))


def plan_owned_agent_goal(
    *,
    owner_id: int,
    goal: Any,
    selected_context: Any = None,
    registry: IntelligenceToolRegistry | None = None,
) -> AgentPlan:
    """Build one owner-validated, bounded, read-only plan.

    The plan is goal-sensitive but deliberately deterministic.  The model reasons
    over the tool observations later; it never invents the tool list or IDs.
    """
    cleaned_goal = _clean_goal(goal)
    try:
        option = validate_owned_ask_context(
            owner_id=int(owner_id), raw_context=selected_context
        )
    except (AskContextValidationError, AskContextNotFoundError):
        raise

    scope = _scope_from_context(option)
    active_registry = registry or DEFAULT_INTELLIGENCE_TOOL_REGISTRY
    text = cleaned_goal.casefold()
    steps: list[AgentPlanStep] = []

    if scope.type == "workspace":
        _append_step(
            steps,
            registry=active_registry,
            step_id="workspace_state",
            tool_name="workspace.get_home",
            arguments={},
            purpose="Establish current priorities, deadlines, document attention and study signals.",
        )
        _append_step(
            steps,
            registry=active_registry,
            step_id="portfolio_review",
            tool_name="workspace.get_portfolio_review",
            arguments={},
            purpose="Rank current project risks and next actions across the owned workspace.",
        )
        if any(word in text for word in ("change", "recent", "today", "week", "overnight", "progress", "happened")):
            _append_step(
                steps,
                registry=active_registry,
                step_id="recent_activity",
                tool_name="workspace.get_recent_activity",
                arguments={},
                purpose="Check recent auditable changes that may affect the goal.",
            )

    elif scope.type == "project":
        assert scope.id is not None
        project_id = int(scope.id)
        _append_step(
            steps,
            registry=active_registry,
            step_id="project_state",
            tool_name="project.get_summary",
            arguments={"project_id": project_id},
            purpose="Establish exact project state, progress, deadline and health.",
        )
        _append_step(
            steps,
            registry=active_registry,
            step_id="project_tasks",
            tool_name="project.get_tasks",
            arguments={"project_id": project_id},
            purpose="Inspect current tasks, blockers, overdue work and upcoming deadlines.",
        )
        _append_step(
            steps,
            registry=active_registry,
            step_id="project_review",
            tool_name="project.review",
            arguments={"project_id": project_id},
            purpose="Use the verified Project Review Agent to rank evidence-backed project priorities.",
        )
        if any(word in text for word in ("document", "deploy", "launch", "risk", "requirement", "spec", "architecture", "knowledge", "ready")):
            _append_step(
                steps,
                registry=active_registry,
                step_id="project_documents",
                tool_name="project.get_documents",
                arguments={"project_id": project_id},
                purpose="Inspect current and stale document intelligence relevant to the goal.",
            )
        if any(word in text for word in ("note", "decision", "context", "remember", "discussion")):
            _append_step(
                steps,
                registry=active_registry,
                step_id="project_notes",
                tool_name="project.get_recent_notes",
                arguments={"project_id": project_id},
                purpose="Include recent user-owned notes and decisions relevant to the goal.",
            )

    elif scope.type in KNOWLEDGE_SCOPE_TYPES:
        assert scope.id is not None
        _append_step(
            steps,
            registry=active_registry,
            step_id="grounded_knowledge",
            tool_name="knowledge.ask_context",
            arguments={
                "context_type": scope.type,
                "context_id": int(scope.id),
                "query": cleaned_goal,
            },
            purpose="Answer the goal through the existing grounded Document Brain/knowledge pipeline.",
        )
    else:
        raise AgentPlannerError("This LifeOS context is not supported by the Agent yet.")

    if not steps:
        raise AgentPlannerError("LifeOS could not build a safe read-only plan for this goal.")
    if len(steps) > MAX_AGENT_PLAN_STEPS:
        raise AgentPlannerError("The agent plan exceeded the reviewed step limit.")

    return AgentPlan(
        version=1,
        goal=cleaned_goal,
        scope=scope,
        planner_mode="constrained_goal_planner",
        steps=tuple(steps),
    )

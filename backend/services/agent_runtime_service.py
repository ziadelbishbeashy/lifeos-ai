"""I19.2-I19.5 — constrained goal-driven LifeOS Agent Runtime.

Flow:
    goal -> owner-validated plan -> reviewed read-only tools -> bounded evidence
    -> one grounded reasoning pass (or trusted fallback) -> audited run
    -> optional I9 action proposal prepared only by explicit user request.

The runtime never gives the model direct tool, ORM, SQL, filesystem, URL, or
workspace mutation access.
"""
from __future__ import annotations

from datetime import date, datetime
import json
import time
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import LifeOSAgentRun
from services.agent_planner_service import AgentPlan, AgentPlannerError, plan_owned_agent_goal
from services.agent_reasoning_service import (
    AgentReasoningError,
    reason_over_agent_observations,
)
from services.intelligence_action_service import (
    IntelligenceActionError,
    create_priority_action_proposal,
    priority_action_options,
    require_owned_proposal,
)
from services.intelligence_tool_registry_service import (
    DEFAULT_INTELLIGENCE_TOOL_REGISTRY,
    IntelligenceToolError,
    IntelligenceToolRegistry,
)

AGENT_LIMITS = {
    "max_steps": 6,
    "max_tool_calls": 6,
    "max_provider_calls": 2,
    "max_runtime_seconds": 45,
    "max_evidence_items": 24,
    "max_action_suggestions": 3,
    "max_history_runs": 30,
}


class AgentRuntimeError(RuntimeError):
    pass


class AgentRunNotFoundError(AgentRuntimeError, LookupError):
    pass


class AgentLimitError(AgentRuntimeError):
    pass


class AgentProposalError(AgentRuntimeError, ValueError):
    pass


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return "[truncated]"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:6000]
    if isinstance(value, dict):
        return {
            str(key)[:120]: _json_safe(item, depth=depth + 1)
            for key, item in list(value.items())[:80]
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, depth=depth + 1) for item in list(value)[:80]]
    return str(value)[:1000]


def _compact_tool_result(tool_name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Keep audit evidence useful without turning agent history into a data dump."""
    if tool_name in {"project.review", "workspace.get_portfolio_review"}:
        return {
            key: _json_safe(data.get(key))
            for key in (
                "kind", "project_id", "project_title", "attention_level",
                "priorities", "reviewed_projects", "total_owned_projects",
                "context_limited", "read_only",
            )
            if key in data
        }
    if tool_name == "workspace.get_home":
        return {
            "today": data.get("today"),
            "briefing": _json_safe(data.get("briefing")),
            "focus": _json_safe(data.get("focus")),
            "deadlines": _json_safe(data.get("deadlines")),
            "documents": _json_safe(data.get("documents")),
            "context_limited": bool(data.get("context_limited")),
            "read_only": True,
        }
    if tool_name == "workspace.get_recent_activity":
        return {
            "summary": data.get("summary"),
            "items": _json_safe(list(data.get("items") or [])[:12]),
            "total_items": data.get("total_items"),
            "context_limited": bool(data.get("context_limited")),
            "read_only": True,
        }
    if tool_name == "knowledge.ask_context":
        grounded = data.get("grounded") if isinstance(data.get("grounded"), dict) else {}
        return {
            "answer": data.get("answer"),
            "response_mode": data.get("response_mode"),
            "verification": _json_safe(data.get("verification")),
            "grounded": {
                "answer": grounded.get("answer"),
                "scope": _json_safe(grounded.get("scope")),
                "sources": _json_safe(list(grounded.get("sources") or [])[:10]),
                "source_count": grounded.get("source_count"),
                "verified_grounding": grounded.get("verified_grounding"),
            },
            "read_only": True,
        }
    if tool_name == "project.get_documents":
        return {
            "documents": _json_safe(list(data.get("documents") or [])[:12]),
            "context_counts": _json_safe(data.get("context_counts")),
        }
    if tool_name == "project.get_tasks":
        return {
            **{
                key: _json_safe(value)
                for key, value in data.items()
                if key != "tasks"
            },
            "tasks": _json_safe(list(data.get("tasks") or [])[:20]),
        }
    return _json_safe(data)


def _clean(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _source_refs(priority: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in list(priority.get("evidence") or [])[:6]:
        if not isinstance(item, dict):
            continue
        result.append({
            "source_type": _clean(item.get("source_type"), 64) or "workspace",
            "source_id": item.get("source_id"),
            "label": _clean(item.get("label"), 255),
            "field": _clean(item.get("field"), 120),
            "freshness": _clean(item.get("freshness"), 40) or "current",
        })
    return result


def _build_evidence_catalog(
    *, plan: AgentPlan, observations: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []

    def add(item: dict[str, Any]) -> None:
        if len(evidence) >= AGENT_LIMITS["max_evidence_items"]:
            return
        evidence.append(item)

    for step in plan.steps:
        data = observations.get(step.step_id) or {}
        if step.tool_name in {"project.review", "workspace.get_portfolio_review"}:
            priorities = list(data.get("priorities") or [])
            for index, priority in enumerate(priorities[:8], start=1):
                if not isinstance(priority, dict):
                    continue
                add({
                    "id": f"{step.step_id}.priority.{index}",
                    "kind": "verified_priority",
                    "label": _clean(priority.get("title"), 300),
                    "detail": _clean(priority.get("reason"), 1200),
                    "severity": _clean(priority.get("severity"), 30),
                    "project_id": priority.get("project_id"),
                    "project_title": _clean(priority.get("project_title"), 255),
                    "source_refs": _source_refs(priority),
                })
            if priorities:
                continue

        if step.tool_name == "workspace.get_home":
            briefing = data.get("briefing") if isinstance(data.get("briefing"), dict) else {}
            add({
                "id": f"{step.step_id}.briefing",
                "kind": "verified_workspace_state",
                "label": _clean(briefing.get("headline"), 300) or "Current LifeOS workspace briefing",
                "detail": _clean(briefing.get("summary"), 1400),
                "attention_level": briefing.get("attention_level"),
                "source_refs": [],
            })
            continue

        if step.tool_name == "workspace.get_recent_activity":
            for index, item in enumerate(list(data.get("items") or [])[:8], start=1):
                if not isinstance(item, dict):
                    continue
                add({
                    "id": f"{step.step_id}.activity.{index}",
                    "kind": "activity",
                    "label": _clean(item.get("title"), 300),
                    "detail": _clean(item.get("summary"), 1000),
                    "source_refs": [{
                        "source_type": item.get("object_type") or "workspace",
                        "source_id": item.get("object_id"),
                        "label": item.get("title") or "Recent activity",
                        "field": item.get("event_type") or "activity",
                        "freshness": "current",
                    }],
                })
            continue

        if step.tool_name == "knowledge.ask_context":
            grounded = data.get("grounded") if isinstance(data.get("grounded"), dict) else {}
            answer = grounded.get("answer") or data.get("answer")
            sources = list(grounded.get("sources") or [])
            if sources:
                for index, source in enumerate(sources[:10], start=1):
                    if not isinstance(source, dict):
                        continue
                    label = source.get("filename") or source.get("label") or f"Knowledge source {index}"
                    detail = source.get("snippet") or source.get("text") or source.get("section") or answer
                    add({
                        "id": f"{step.step_id}.source.{index}",
                        "kind": "grounded_knowledge",
                        "label": _clean(label, 300),
                        "detail": _clean(detail, 1400),
                        "source_refs": [_json_safe(source)],
                    })
            else:
                add({
                    "id": f"{step.step_id}.answer",
                    "kind": "grounded_knowledge",
                    "label": f"Grounded answer from {plan.scope.label}",
                    "detail": _clean(answer, 1800),
                    "source_refs": [],
                })
            continue

        # Generic trusted observation for exact structured state tools.
        add({
            "id": f"{step.step_id}.result",
            "kind": "trusted_tool_result",
            "label": step.purpose,
            "detail": _clean(json.dumps(_compact_tool_result(step.tool_name, data), ensure_ascii=False), 1800),
            "source_refs": [],
        })

    return evidence[: AGENT_LIMITS["max_evidence_items"]]


def _action_suggestions(observations: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for data in observations.values():
        priorities = data.get("priorities") if isinstance(data, dict) else None
        if not isinstance(priorities, list):
            continue
        for priority in priorities:
            if not isinstance(priority, dict) or priority.get("project_id") is None:
                continue
            key = (
                priority.get("project_id"),
                str(priority.get("category") or ""),
                str(priority.get("title") or "").casefold(),
            )
            if key in seen:
                continue
            seen.add(key)
            options = priority_action_options(priority)
            suggestions.append({
                "id": f"action-{len(suggestions) + 1}",
                "title": _clean(priority.get("title"), 300),
                "reason": _clean(priority.get("reason"), 1600),
                "recommended_action": _clean(priority.get("recommended_action"), 1200),
                "severity": _clean(priority.get("severity"), 30) or "medium",
                "project_id": int(priority.get("project_id")),
                "project_title": _clean(priority.get("project_title"), 255),
                "options": options,
                # Persist the exact server-derived priority so a later explicit
                # prepare call can reuse the existing I9 service safely.
                "priority": _json_safe(priority),
            })
            if len(suggestions) >= AGENT_LIMITS["max_action_suggestions"]:
                return suggestions
    return suggestions


_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "normal": 0, "": 0}


def _severity_rank(value: Any) -> int:
    return _SEVERITY_RANK.get(_clean(value, 30).casefold(), 0)


def _goal_summary(
    *,
    plan: AgentPlan,
    evidence: list[dict[str, Any]],
    reasoning: dict[str, Any],
    suggestions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a stable executive summary from verified runtime output.

    The LLM may phrase the final answer, but code decides which findings are
    surfaced as the biggest blocker, which source labels are counted, and how
    many recommendations/actions are exposed. This keeps the user-facing goal
    review concise and deterministic even when provider prose varies.
    """
    findings = [item for item in evidence if item.get("kind") == "verified_priority"]
    ranked = sorted(
        enumerate(findings),
        key=lambda pair: (-_severity_rank(pair[1].get("severity")), pair[0]),
    )
    ordered = [item for _, item in ranked]
    biggest = ordered[0] if ordered else None

    high_count = sum(1 for item in ordered if _severity_rank(item.get("severity")) >= 3)
    medium_count = sum(1 for item in ordered if _severity_rank(item.get("severity")) == 2)
    if high_count:
        status = "at_risk"
        status_label = "At risk"
        headline = f"{high_count} high-priority {('finding needs' if high_count == 1 else 'findings need')} attention before this goal is ready."
    elif medium_count:
        status = "needs_attention"
        status_label = "Needs attention"
        headline = f"{medium_count} important {('finding needs' if medium_count == 1 else 'findings need')} attention before moving forward."
    elif ordered:
        status = "on_track"
        status_label = "On track with follow-up"
        headline = f"LifeOS found {len(ordered)} lower-risk {('finding' if len(ordered) == 1 else 'findings')} to keep in view."
    else:
        status = "insufficient_evidence"
        status_label = "Needs more evidence"
        headline = "LifeOS completed the checks but did not find enough verified priority evidence to make a stronger readiness call."

    recommendations: list[str] = []
    for item in list(reasoning.get("recommendations") or []):
        if not isinstance(item, dict):
            continue
        text = _clean(item.get("text"), 900)
        if text and text.casefold() not in {entry.casefold() for entry in recommendations}:
            recommendations.append(text)
        if len(recommendations) >= 3:
            break
    if len(recommendations) < 3:
        for suggestion in suggestions:
            text = _clean(suggestion.get("recommended_action"), 900)
            if text and text.casefold() not in {entry.casefold() for entry in recommendations}:
                recommendations.append(text)
            if len(recommendations) >= 3:
                break

    source_labels: list[str] = []
    for item in evidence:
        for ref in list(item.get("source_refs") or []):
            if not isinstance(ref, dict):
                continue
            label = _clean(ref.get("label") or ref.get("filename"), 255)
            if label and label.casefold() not in {entry.casefold() for entry in source_labels}:
                source_labels.append(label)

    biggest_payload = None
    if biggest is not None:
        biggest_payload = {
            "title": _clean(biggest.get("label"), 500),
            "why": _clean(biggest.get("detail"), 1600),
            "severity": _clean(biggest.get("severity"), 30) or "medium",
            "project_title": _clean(biggest.get("project_title"), 255),
            "evidence_id": biggest.get("id"),
        }

    other_risks = [
        {
            "title": _clean(item.get("label"), 500),
            "why": _clean(item.get("detail"), 1200),
            "severity": _clean(item.get("severity"), 30) or "medium",
            "evidence_id": item.get("id"),
        }
        for item in ordered[1:4]
        if _clean(item.get("label"), 500)
    ]

    return {
        "status": status,
        "status_label": status_label,
        "headline": headline,
        "scope_label": plan.scope.label,
        "biggest_blocker": biggest_payload,
        "other_risks": other_risks,
        "focus_steps": recommendations[:3],
        "finding_count": len(ordered),
        "source_count": len(source_labels),
        "source_labels": source_labels[:8],
    }


def _trusted_fallback_answer(
    *, plan: AgentPlan, observations: dict[str, dict[str, Any]], evidence: list[dict[str, Any]]
) -> dict[str, Any]:
    knowledge = observations.get("grounded_knowledge")
    if knowledge:
        answer = _clean(knowledge.get("answer"), 5000)
        if answer:
            ids = [item["id"] for item in evidence[:4]]
            return {
                "answer": answer,
                "claims": [{"text": answer, "evidence_ids": ids}] if ids else [],
                "recommendations": [],
                "verification_status": "trusted_grounded_fallback",
                "reasoning_mode": "existing_grounded_knowledge",
            }

    for step_id in ("project_review", "portfolio_review"):
        review = observations.get(step_id)
        if isinstance(review, dict) and review.get("priorities"):
            top = list(review.get("priorities") or [])[0]
            title = _clean(top.get("title"), 500)
            reason = _clean(top.get("reason"), 1500)
            project = _clean(top.get("project_title"), 255)
            answer = f"Top focus{f' for {project}' if project else ''}: {title}."
            if reason:
                answer += f" {reason}"
            evidence_id = next((item["id"] for item in evidence if item.get("kind") == "verified_priority"), None)
            return {
                "answer": answer,
                "claims": ([{"text": answer, "evidence_ids": [evidence_id]}] if evidence_id else []),
                "recommendations": [],
                "verification_status": "trusted_fallback",
                "reasoning_mode": "verified_priority_fallback",
            }

    home = observations.get("workspace_state")
    if isinstance(home, dict):
        briefing = home.get("briefing") if isinstance(home.get("briefing"), dict) else {}
        answer = " ".join(
            part for part in (_clean(briefing.get("headline"), 500), _clean(briefing.get("summary"), 1400)) if part
        )
        if answer:
            evidence_id = next((item["id"] for item in evidence if item["id"].startswith("workspace_state.")), None)
            return {
                "answer": answer,
                "claims": ([{"text": answer, "evidence_ids": [evidence_id]}] if evidence_id else []),
                "recommendations": [],
                "verification_status": "trusted_fallback",
                "reasoning_mode": "workspace_briefing_fallback",
            }

    return {
        "answer": "LifeOS completed the read-only checks, but the available evidence was not sufficient to produce a stronger conclusion for this goal.",
        "claims": [],
        "recommendations": [],
        "verification_status": "insufficient_evidence",
        "reasoning_mode": "safe_empty_fallback",
    }


def _knowledge_result_is_direct(plan: AgentPlan) -> bool:
    return len(plan.steps) == 1 and plan.steps[0].tool_name == "knowledge.ask_context"


def _save_run(run: LifeOSAgentRun) -> None:
    try:
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise AgentRuntimeError("LifeOS could not save the agent run audit record.") from error


def run_owned_agent_goal(
    *,
    owner_id: int,
    goal: Any,
    selected_context: Any = None,
    registry: IntelligenceToolRegistry | None = None,
) -> LifeOSAgentRun:
    plan = plan_owned_agent_goal(
        owner_id=int(owner_id), goal=goal, selected_context=selected_context, registry=registry
    )
    if len(plan.steps) > AGENT_LIMITS["max_steps"]:
        raise AgentLimitError("The agent plan exceeded the maximum step limit.")

    run = LifeOSAgentRun(
        user_id=int(owner_id),
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

    active_registry = registry or DEFAULT_INTELLIGENCE_TOOL_REGISTRY
    started_clock = time.monotonic()
    observations: dict[str, dict[str, Any]] = {}
    trace: list[dict[str, Any]] = []
    tool_calls = 0
    provider_calls = 0

    try:
        for index, step in enumerate(plan.steps, start=1):
            if tool_calls >= AGENT_LIMITS["max_tool_calls"]:
                raise AgentLimitError("The agent reached its tool-call limit.")
            if time.monotonic() - started_clock > AGENT_LIMITS["max_runtime_seconds"]:
                raise AgentLimitError("The agent reached its runtime limit.")

            step_started = time.monotonic()
            try:
                result = active_registry.execute(
                    step.tool_name,
                    owner_id=int(owner_id),
                    arguments=step.arguments,
                    allow_mutation=False,
                )
                tool_calls += 1
                if step.tool_name == "knowledge.ask_context":
                    # Conservatively reserve the full I4/I5 grounded Ask LifeOS
                    # budget. The direct knowledge path never adds another reasoner.
                    provider_calls += 2
                observations[step.step_id] = result.data
                trace.append({
                    "index": index,
                    "step_id": step.step_id,
                    "tool_name": step.tool_name,
                    "purpose": step.purpose,
                    "status": "succeeded",
                    "duration_ms": round((time.monotonic() - step_started) * 1000, 2),
                    "result": _compact_tool_result(step.tool_name, result.data),
                })
            except Exception as error:
                trace.append({
                    "index": index,
                    "step_id": step.step_id,
                    "tool_name": step.tool_name,
                    "purpose": step.purpose,
                    "status": "failed",
                    "duration_ms": round((time.monotonic() - step_started) * 1000, 2),
                    "error": _clean(error, 1200),
                })
                raise

        evidence = _build_evidence_catalog(plan=plan, observations=observations)
        suggestions = _action_suggestions(observations)[:2]

        if time.monotonic() - started_clock > AGENT_LIMITS["max_runtime_seconds"]:
            raise AgentLimitError("The agent reached its runtime limit before final reasoning.")

        if _knowledge_result_is_direct(plan):
            reasoning = _trusted_fallback_answer(plan=plan, observations=observations, evidence=evidence)
            provider = None
            model = None
        else:
            if provider_calls >= AGENT_LIMITS["max_provider_calls"]:
                raise AgentLimitError("The agent reached its AI-call limit before final reasoning.")
            provider_calls += 1
            try:
                reasoned = reason_over_agent_observations(
                    goal=plan.goal,
                    scope=plan.scope.to_dict(),
                    evidence_catalog=evidence,
                )
                reasoning = {
                    **reasoned.to_dict(),
                    "verification_status": "verified_evidence_ids",
                    "reasoning_mode": "provider_reasoning",
                }
                provider = reasoned.provider
                model = reasoned.model
                if time.monotonic() - started_clock > AGENT_LIMITS["max_runtime_seconds"]:
                    raise AgentLimitError("The agent reached its runtime limit during final reasoning.")
            except AgentReasoningError as error:
                reasoning = _trusted_fallback_answer(plan=plan, observations=observations, evidence=evidence)
                reasoning["provider_failure"] = _clean(error, 1000)
                provider = None
                model = None

        goal_summary = _goal_summary(
            plan=plan, evidence=evidence, reasoning=reasoning, suggestions=suggestions
        )

        run.status = "succeeded"
        run.trace_json = json.dumps(_json_safe(trace), ensure_ascii=False)
        run.output_json = json.dumps({
            "answer": reasoning.get("answer"),
            "goal_summary": goal_summary,
            "claims": reasoning.get("claims") or [],
            "recommendations": reasoning.get("recommendations") or [],
            "verification_status": reasoning.get("verification_status"),
            "reasoning_mode": reasoning.get("reasoning_mode"),
            "provider_failure": reasoning.get("provider_failure"),
            "evidence": evidence,
            "action_suggestions": suggestions,
            "prepared_proposals": [],
            "read_only": True,
            "workspace_mutation": False,
            "confirmation_boundary": "I9",
            "context_limited": any(bool((observations.get(step.step_id) or {}).get("context_limited")) for step in plan.steps),
        }, ensure_ascii=False)
        run.provider = provider
        run.model = model
        run.provider_calls = provider_calls
        run.tool_calls = tool_calls
        run.finished_at = datetime.utcnow()
        run.failure_message = None
        _save_run(run)
        return run

    except Exception as error:
        # The broad catch is intentional at this boundary: the error is reduced
        # to a user-safe audit message and no workspace mutation can have happened.
        run.status = "failed"
        run.trace_json = json.dumps(_json_safe(trace), ensure_ascii=False)
        run.output_json = json.dumps({
            "answer": None,
            "evidence": _build_evidence_catalog(plan=plan, observations=observations),
            "action_suggestions": [],
            "prepared_proposals": [],
            "read_only": True,
            "workspace_mutation": False,
            "confirmation_boundary": "I9",
        }, ensure_ascii=False)
        run.provider_calls = provider_calls
        run.tool_calls = tool_calls
        run.finished_at = datetime.utcnow()
        run.failure_message = _clean(error, 1600) or "The agent run failed."
        _save_run(run)
        return run


def require_owned_agent_run(*, owner_id: int, run_id: int) -> LifeOSAgentRun:
    run = LifeOSAgentRun.query.filter_by(id=int(run_id), user_id=int(owner_id)).first()
    if run is None:
        raise AgentRunNotFoundError("Agent run not found.")
    return run


def agent_run_to_dict(run: LifeOSAgentRun, *, include_trace: bool = True) -> dict[str, Any]:
    return {
        "id": int(run.id),
        "goal": run.goal,
        "scope": {"type": run.scope_type, "id": run.scope_id, "label": run.scope_label},
        "status": run.status,
        "plan": run.plan,
        "trace": run.trace if include_trace else [],
        "output": run.output,
        "limits": run.limits,
        "metrics": {
            "tool_calls": int(run.tool_calls or 0),
            "provider_calls": int(run.provider_calls or 0),
            "provider": run.provider,
            "model": run.model,
        },
        "failure_message": run.failure_message if run.status == "failed" else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "safety": {
            "read_only_execution": True,
            "workspace_mutation": False,
            "important_actions_require": "I9_confirmation",
        },
    }


def list_owned_agent_runs(*, owner_id: int, limit: int = 12) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 12), AGENT_LIMITS["max_history_runs"]))
    rows = (
        LifeOSAgentRun.query
        .filter_by(user_id=int(owner_id))
        .order_by(LifeOSAgentRun.id.desc())
        .limit(safe_limit)
        .all()
    )
    return [agent_run_to_dict(row, include_trace=False) for row in rows]


def prepare_agent_action_proposal(
    *, owner_id: int, run_id: int, suggestion_id: str, action_type: str
):
    """Prepare, but never execute, an I9 proposal from trusted agent output."""
    run = require_owned_agent_run(owner_id=int(owner_id), run_id=int(run_id))
    if run.status != "succeeded":
        raise AgentProposalError("Only a successful agent run can prepare an action proposal.")
    output = dict(run.output)
    prepared_existing = list(output.get("prepared_proposals") or [])
    for prepared_item in prepared_existing:
        if not isinstance(prepared_item, dict):
            continue
        if prepared_item.get("suggestion_id") != suggestion_id or prepared_item.get("action_type") != action_type:
            continue
        try:
            existing = require_owned_proposal(
                proposal_id=int(prepared_item.get("proposal_id")), owner_id=int(owner_id)
            )
        except (ValueError, TypeError, IntelligenceActionError):
            existing = None
        if existing is not None and existing.status in {"pending", "executing", "confirmed"}:
            return existing

    suggestions = list(output.get("action_suggestions") or [])
    suggestion = next(
        (item for item in suggestions if isinstance(item, dict) and item.get("id") == suggestion_id),
        None,
    )
    if suggestion is None:
        raise AgentProposalError("That agent suggestion is not available on this run.")
    allowed = {item.get("type") for item in list(suggestion.get("options") or []) if isinstance(item, dict)}
    if action_type not in allowed:
        raise AgentProposalError("That action is not allowed for this verified suggestion.")
    priority = suggestion.get("priority")
    if not isinstance(priority, dict):
        raise AgentProposalError("The verified priority behind this suggestion is unavailable.")

    try:
        proposal = create_priority_action_proposal(
            owner_id=int(owner_id), action_type=str(action_type), priority=priority
        )
    except IntelligenceActionError as error:
        raise AgentProposalError(str(error)) from error

    prepared = prepared_existing
    prepared.append({
        "suggestion_id": suggestion_id,
        "proposal_id": int(proposal.id),
        "action_type": proposal.action_type,
        "status": proposal.status,
    })
    output["prepared_proposals"] = prepared[-10:]
    run.output_json = json.dumps(_json_safe(output), ensure_ascii=False)
    _save_run(run)
    return proposal


def agent_registry_payload() -> dict[str, Any]:
    contracts = [
        item for item in DEFAULT_INTELLIGENCE_TOOL_REGISTRY.list_contracts()
        if not item.get("mutates_state")
    ]
    return {
        "phase": "I19",
        "runtime": "constrained_goal_agent",
        "supported_scopes": ["workspace", "project", "document", "collection", "module", "lecture"],
        "tools": contracts,
        "limits": dict(AGENT_LIMITS),
        "safety": {
            "direct_database_access": False,
            "arbitrary_tool_access": False,
            "arbitrary_code": False,
            "arbitrary_sql": False,
            "workspace_mutation": False,
            "action_proposals_require_i9_confirmation": True,
        },
    }

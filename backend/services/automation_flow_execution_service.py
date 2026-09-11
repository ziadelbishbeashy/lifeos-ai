"""I18.3–I18.6 compiled visual-flow execution adapter.

The adapter executes only backend-compiled, allow-listed LifeOS capabilities.
It is intentionally not a second automation engine: I17 still owns run audit,
scheduling/event candidate selection, status transitions, and notification
materialization.  This module only interprets the constrained compiled plan.

No node can execute arbitrary code/SQL/URLs or write workspace resources.  I9
proposal nodes may persist a *pending* LifeOSActionProposal on a real run; the
actual workspace mutation still requires the existing explicit I9 confirmation.
"""
from __future__ import annotations

from datetime import datetime
from time import perf_counter
from typing import Any

from models import (
    Document,
    DocumentCollection,
    LearningModule,
    LifeOSActionProposal,
    LifeOSAutomation,
    LifeOSIntelligenceEvent,
    Project,
)
from services.automation_intelligence_service import (
    build_event_context_review_output,
    build_risk_escalation_output,
    build_today_briefing_output,
    build_unhandled_followup_output,
    build_weekly_review_output,
)
from services.intelligence_action_service import (
    ACTION_CREATE_NOTE,
    ACTION_CREATE_TASK,
    ACTION_REFRESH_DOCUMENT_ANALYSIS,
    create_priority_action_proposal,
    priority_action_options,
    proposal_to_dict,
)
from services.intelligence_ask_service import ask_lifeos
from services.lifeos_activity_service import build_owned_recent_activity
from services.project_review_agent_service import (
    run_owned_portfolio_review_agent,
    run_owned_project_review_agent,
)


class AutomationFlowExecutionError(RuntimeError):
    def __init__(self, message: str, *, trace: list[dict[str, Any]], failed_node_id: str | None = None):
        super().__init__(message)
        self.trace = trace
        self.failed_node_id = failed_node_id

    def audit_output(self) -> dict[str, Any]:
        return {
            "kind": "compiled_visual_flow_failure",
            "summary": str(self),
            "flow_trace": self.trace,
            "failed_node_id": self.failed_node_id,
            "verified_from_state": True,
            "workspace_mutation": False,
        }


def _owned(model: Any, *, owner_id: int, resource_id: Any, label: str) -> Any:
    try:
        parsed = int(resource_id)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} context is missing a valid id.") from error
    row = model.query.filter_by(id=parsed, user_id=int(owner_id)).first()
    if row is None:
        raise ValueError(f"{label} context is no longer available in this workspace.")
    return row


def _compact(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"value": str(value)[:500]}
    result: dict[str, Any] = {}
    for key in (
        "kind", "title", "summary", "answer", "attention_level", "priority_count",
        "activity_count", "source_count", "verified_from_state", "read_only",
        "proposal", "suggestion", "scope", "condition_passed", "continue_flow",
        "reused_previous_step", "response_mode", "ai_provider_calls",
    ):
        if key in value and value[key] is not None:
            current = value[key]
            if isinstance(current, str):
                current = current[:1400]
            result[key] = current
    if "priorities" in value and isinstance(value["priorities"], list):
        result["priorities"] = value["priorities"][:3]
    if "escalations" in value and isinstance(value["escalations"], list):
        result["escalations"] = value["escalations"][:3]
    if "items" in value and isinstance(value["items"], list):
        result["items"] = value["items"][:3]
    return result


def _project_review_output(*, owner_id: int, project_id: int) -> dict[str, Any]:
    result = run_owned_project_review_agent(project_id=int(project_id), owner_id=int(owner_id)).to_dict(include_diagnostics=False)
    priorities = list(result.get("priorities") or [])
    title = f"Project review ready: {result.get('project_title') or 'Project'}"
    summary = f"Reviewed {result.get('project_title') or 'the project'} and found {len(priorities)} ranked priorit{'y' if len(priorities) == 1 else 'ies'}."
    if priorities:
        summary += f" Top focus: {priorities[0].get('title')}."
    return {
        "kind": "project_review",
        "project_id": int(project_id),
        "title": title,
        "summary": summary,
        "attention_level": result.get("attention_level"),
        "priorities": priorities[:5],
        "priority_count": len(priorities),
        "verified_from_state": True,
        "read_only": True,
    }


_FAST_PROJECT_QUESTION_TERMS = (
    "risk", "risky", "blocker", "blocked", "blocking", "block ", "delay", "delayed",
    "unresolved issue", "unresolved blocker", "launch blocker", "delivery risk",
)


def _fast_project_custom_answer(*, owner_id: int, project_id: int, instruction: str) -> dict[str, Any] | None:
    """Answer common project-priority questions without spending an LLM call.

    The existing project review agent already derives ranked priorities from trusted
    LifeOS state.  Visual automations should use that deterministic intelligence for
    common blocker/risk/focus questions and reserve provider calls for genuinely
    open-ended language reasoning.
    """

    normalized = " ".join(str(instruction or "").casefold().split())
    if not any(term in normalized for term in _FAST_PROJECT_QUESTION_TERMS):
        return None

    review = run_owned_project_review_agent(project_id=int(project_id), owner_id=int(owner_id)).to_dict(include_diagnostics=False)
    priorities = list(review.get("priorities") or [])
    if priorities:
        top = priorities[0]
        title = str(top.get("title") or "Top project priority")
        reason = " ".join(str(top.get("reason") or "").split())
        recommended = " ".join(str(top.get("recommended_action") or "").split())
        answer = title
        if reason:
            answer += f". {reason}"
        if recommended:
            answer += f" Recommended next step: {recommended}"
    else:
        answer = "LifeOS did not find a concrete blocker, overdue item, near deadline, stale document warning, or other ranked priority in the trusted project state."

    return {
        "kind": "custom_ask_project_fast",
        "title": "LifeOS answered from verified project intelligence",
        "summary": answer[:1800],
        "answer": answer[:1800],
        "attention_level": review.get("attention_level"),
        "priorities": priorities[:5],
        "priority_count": len(priorities),
        "response_mode": "agent_verified_fast",
        "verification": {
            "status": "verified",
            "deterministic_checks_passed": True,
            "prose_check_performed": False,
            "policy": "automation_deterministic_fast_path",
        },
        "verified_from_state": True,
        "read_only": True,
        "ai_provider_calls": 0,
    }


def _priority_rows(*, owner_id: int, project_id: int | None) -> list[dict[str, Any]]:
    if project_id is not None:
        review = run_owned_project_review_agent(project_id=int(project_id), owner_id=int(owner_id))
        return [item.to_dict(include_diagnostics=False) for item in review.priorities]
    review = run_owned_portfolio_review_agent(owner_id=int(owner_id))
    return [item.to_dict(include_diagnostics=False) for item in review.priorities]


def _priority_from_current_result_for_note(*, state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any] | None:
    project_id = state.get("project_id")
    try:
        project_id = int(project_id) if project_id is not None else None
    except (TypeError, ValueError):
        project_id = None
    if not project_id:
        return None
    reason = str(result.get("answer") or result.get("summary") or "").strip()
    if not reason:
        return None
    title = str(result.get("title") or "Automation insight").strip()[:220]
    evidence: list[dict[str, Any]] = [{
        "source_type": "project",
        "source_id": project_id,
        "label": str((state.get("scope") or {}).get("label") or "Selected project"),
        "field": "automation_verified_result",
        "freshness": "current",
    }]
    if state.get("document_id") is not None:
        evidence.append({
            "source_type": "document",
            "source_id": int(state["document_id"]),
            "label": str((state.get("scope") or {}).get("label") or "Selected document"),
            "field": "grounded_automation_result",
            "freshness": "current",
        })
    return {
        "category": "automation_insight",
        "title": title,
        "reason": reason[:1600],
        "recommended_action": "Save this verified automation result as a note for later reference.",
        "severity": str(result.get("attention_level") or "medium"),
        "project_id": project_id,
        "evidence": evidence,
    }


def _pending_matching_proposal(*, owner_id: int, action_type: str, priority: dict[str, Any]) -> LifeOSActionProposal | None:
    try:
        project_id = int(priority.get("project_id"))
    except (TypeError, ValueError):
        return None
    reason = " ".join(str(priority.get("reason") or "").split())
    rows = LifeOSActionProposal.query.filter_by(
        user_id=int(owner_id),
        action_type=action_type,
        status="pending",
        project_id=project_id,
    ).order_by(LifeOSActionProposal.id.desc()).limit(10).all()
    if not reason:
        return rows[0] if rows else None
    return next((row for row in rows if " ".join(str(row.reason or "").split()) == reason), None)


def _notification_from_result(result: dict[str, Any], automation: LifeOSAutomation) -> dict[str, Any]:
    existing = result.get("notification") if isinstance(result, dict) else None
    if isinstance(existing, dict):
        return dict(existing)
    title = str(result.get("title") or f"{automation.name} completed")[:255]
    summary = str(result.get("summary") or result.get("answer") or "LifeOS completed this visual intelligence flow from verified state.")[:2000]
    attention = str(result.get("attention_level") or "normal").casefold()
    severity = "high" if attention in {"high", "critical"} else "medium" if attention == "medium" else "info"
    return {
        "should_notify": True,
        "event_type": "automation.visual_flow_ready",
        "severity": severity,
        "title": title,
        "message": summary,
        "dedupe_scope": "run",
        "action_label": "Open Automations",
        "action_href": "/automations",
        "ask_query": "Summarize the latest LifeOS automation result.",
    }


def _selected_context_from_state(state: dict[str, Any]) -> dict[str, Any] | None:
    scope = state.get("scope") if isinstance(state.get("scope"), dict) else {}
    kind = str(scope.get("type") or "workspace")
    if kind in {"project", "document", "module", "collection"}:
        try:
            resource_id = int(scope.get("id"))
        except (TypeError, ValueError):
            return None
        if resource_id > 0:
            return {"type": kind, "id": resource_id}
    return None


def _result_has_content(result: dict[str, Any]) -> bool:
    count_keys = ("priority_count", "activity_count", "source_count", "finding_count", "item_count")
    count_signal_present = any(key in result for key in count_keys)
    for key in count_keys:
        try:
            if int(result.get(key) or 0) > 0:
                return True
        except (TypeError, ValueError):
            pass
    for key in ("priorities", "items", "findings", "escalations", "sources"):
        value = result.get(key)
        if isinstance(value, list) and len(value) > 0:
            return True
    # If a deterministic step explicitly reported one or more count fields and
    # all of them are zero, do not let a generic summary such as “0 risks found”
    # accidentally pass the gate.
    if count_signal_present:
        return False
    answer = str(result.get("answer") or "").strip()
    if answer and answer.casefold() not in {"none", "no findings", "nothing found"}:
        return True
    return False


def _attention_value(result: dict[str, Any]) -> int:
    levels = {"none": 0, "normal": 0, "info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    explicit = levels.get(str(result.get("attention_level") or "").strip().casefold(), 0)
    if explicit:
        return explicit
    # Many deterministic intelligence results express importance through ranked
    # priorities rather than an explicit attention_level. Treat real findings as
    # medium attention, but never manufacture a high/critical signal.
    if _result_has_content(result) and (result.get("priorities") or result.get("escalations") or result.get("findings")):
        return 2
    return 0


def _gate_result(*, passed: bool, label: str, reason: str, previous: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "automation_condition",
        "title": label,
        "summary": reason,
        "condition_passed": bool(passed),
        "continue_flow": bool(passed),
        "checked_result": _compact(previous),
        "verified_from_state": True,
        "read_only": True,
        "workspace_mutation": False,
    }


def execute_compiled_visual_flow(
    *,
    owner_id: int,
    automation: LifeOSAutomation,
    compiled_plan: dict[str, Any],
    event_id: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute one backend-compiled linear plan through approved service bindings."""

    event: LifeOSIntelligenceEvent | None = None
    if event_id is not None:
        event = LifeOSIntelligenceEvent.query.filter_by(id=int(event_id), user_id=int(owner_id)).first()
        if event is None:
            raise ValueError("Trigger event was not found.")

    state: dict[str, Any] = {
        "scope": {"type": "workspace"},
        "project_id": None,
        "document_id": None,
        "module_id": None,
        "collection_id": None,
        "recent_activity": None,
        "result": {},
        "suggestion": None,
        "proposal": None,
        "step_results": {},
        "last_node_id": None,
        "halted": False,
        "halt_reason": None,
    }
    trace: list[dict[str, Any]] = []
    plan_steps = list(compiled_plan.get("steps") or [])

    for step_index, step in enumerate(plan_steps):
        node_id = str(step.get("node_id") or "")
        capability = str(step.get("capability") or "")
        started = datetime.utcnow()
        tick = perf_counter()
        previous_node_id = state.get("last_node_id")
        previous_result = state.get("result") if isinstance(state.get("result"), dict) else {}
        trace_item: dict[str, Any] = {
            "index": int(step.get("index") or 0),
            "node_id": node_id,
            "node_type": str(step.get("node_type") or ""),
            "label": str(step.get("label") or capability),
            "capability": capability,
            "service_boundary": str(step.get("service_boundary") or ""),
            "status": "running",
            "started_at": started.isoformat(),
            "input_from_node_id": previous_node_id,
            "input_summary": str(previous_result.get("summary") or previous_result.get("answer") or "")[:500] or None,
        }
        trace.append(trace_item)
        try:
            config = dict(step.get("config") or {})
            result: dict[str, Any] = {}

            if capability.startswith("schedule.") or capability.startswith("event.") or capability == "manual.run":
                result = {"kind": "trigger", "trigger_source": capability, "verified_from_state": True}

            elif capability == "context.all_lifeos":
                state.update({"scope": {"type": "workspace"}, "project_id": None, "document_id": None, "module_id": None, "collection_id": None})
                result = {"kind": "context", "scope": state["scope"], "verified_from_state": True}

            elif capability == "context.project":
                project_id = event.project_id if config.get("scope_mode") == "trigger" and event is not None else config.get("project_id")
                project = _owned(Project, owner_id=owner_id, resource_id=project_id, label="Project")
                state["project_id"] = int(project.id)
                state["scope"] = {"type": "project", "id": int(project.id), "label": str(project.title)}
                result = {"kind": "context", "scope": state["scope"], "verified_from_state": True}

            elif capability == "context.document":
                document_id = event.object_id if config.get("scope_mode") == "trigger" and event is not None and event.object_type == "document" else config.get("document_id")
                document = _owned(Document, owner_id=owner_id, resource_id=document_id, label="Document")
                if not bool(getattr(document, "is_current_version", True)):
                    raise ValueError("Document Context must resolve to the current document version.")
                state["document_id"] = int(document.id)
                state["project_id"] = int(document.project_id) if document.project_id is not None else state.get("project_id")
                state["scope"] = {"type": "document", "id": int(document.id), "label": str(document.filename)}
                result = {"kind": "context", "scope": state["scope"], "verified_from_state": True}

            elif capability == "context.module":
                module = _owned(LearningModule, owner_id=owner_id, resource_id=config.get("module_id"), label="Module")
                state["module_id"] = int(module.id)
                state["scope"] = {"type": "module", "id": int(module.id), "label": str(module.title)}
                result = {"kind": "context", "scope": state["scope"], "verified_from_state": True}

            elif capability == "context.collection":
                collection = _owned(DocumentCollection, owner_id=owner_id, resource_id=config.get("collection_id"), label="Collection")
                state["collection_id"] = int(collection.id)
                state["scope"] = {"type": "collection", "id": int(collection.id), "label": str(collection.name)}
                result = {"kind": "context", "scope": state["scope"], "verified_from_state": True}

            elif capability == "context.recent_activity":
                query = "What changed today?" if config.get("window") == "today" else "What changed this week?"
                activity = build_owned_recent_activity(owner_id=owner_id, query=query, project_id=state.get("project_id"))
                state["recent_activity"] = activity.to_dict()
                result = {"kind": "recent_activity_context", "summary": activity.summary, "items": state["recent_activity"].get("items", [])[:5], "verified_from_state": True}

            elif capability == "intelligence.today_briefing":
                result = build_today_briefing_output(owner_id=owner_id)

            elif capability == "intelligence.portfolio_review":
                result = build_weekly_review_output(owner_id=owner_id)

            elif capability == "intelligence.project_review":
                project_id = config.get("project_id") or state.get("project_id")
                project = _owned(Project, owner_id=owner_id, resource_id=project_id, label="Project")
                state["project_id"] = int(project.id)
                result = _project_review_output(owner_id=owner_id, project_id=int(project.id))

            elif capability == "intelligence.detect_risks":
                if state.get("project_id"):
                    # Reuse the verified project review immediately before this
                    # node when available. This makes visual steps genuinely pass
                    # work forward instead of repeating the same review call.
                    if previous_result.get("kind") == "project_review" and int(previous_result.get("project_id") or 0) == int(state["project_id"]):
                        review = previous_result
                        reused_previous_step = True
                    else:
                        review = _project_review_output(owner_id=owner_id, project_id=int(state["project_id"]))
                        reused_previous_step = False
                    priorities = [p for p in list(review.get("priorities") or []) if str(p.get("severity") or "").casefold() in {"high", "medium", "critical"}]
                    result = {
                        "kind": "project_risk_review",
                        "project_id": int(state["project_id"]),
                        "title": "Project risk evaluation complete",
                        "summary": (f"LifeOS found {len(priorities)} medium-or-higher ranked project signal{'s' if len(priorities) != 1 else ''}."),
                        "attention_level": review.get("attention_level"),
                        "priorities": priorities[:5],
                        "priority_count": len(priorities),
                        "reused_previous_step": reused_previous_step,
                        "verified_from_state": True,
                        "read_only": True,
                    }
                else:
                    result = build_risk_escalation_output(owner_id=owner_id)

            elif capability == "intelligence.find_unhandled_findings":
                result = build_unhandled_followup_output(owner_id=owner_id)

            elif capability == "intelligence.event_context_review":
                if event is None:
                    raise ValueError("Review Triggering Event requires a verified I14 event run.")
                result = build_event_context_review_output(owner_id=owner_id, event=event)

            elif capability == "intelligence.review_document":
                selected_context = _selected_context_from_state(state)
                if selected_context is None or selected_context.get("type") not in {"document", "collection", "module"}:
                    raise ValueError("Review Knowledge requires a Document, Collection, or Module Context earlier in the flow.")
                asked = ask_lifeos(
                    query="Review this knowledge source. Summarize the most important findings, risks, and actionable points using only grounded evidence from the selected context.",
                    owner_id=owner_id,
                    selected_context=selected_context,
                )
                payload = asked.to_dict(include_diagnostics=False)
                result = {
                    "kind": "grounded_knowledge_review",
                    "title": "Knowledge review complete",
                    "summary": str(payload.get("answer") or "Knowledge review completed."),
                    "answer": payload.get("answer"),
                    "grounded": payload.get("grounded"),
                    "verification": payload.get("verification"),
                    "source_count": int(((payload.get("grounded") or {}).get("source_count") or 0)) if isinstance(payload.get("grounded"), dict) else 0,
                    "verified_from_state": True,
                    "read_only": True,
                }

            elif capability == "intelligence.rank_priorities":
                previous_priorities = previous_result.get("priorities") if isinstance(previous_result.get("priorities"), list) else None
                if previous_priorities is not None:
                    priorities = list(previous_priorities)
                    reused_previous_step = True
                else:
                    priorities = _priority_rows(owner_id=owner_id, project_id=state.get("project_id"))
                    reused_previous_step = False
                severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
                priorities.sort(key=lambda item: severity_order.get(str((item or {}).get("severity") or "").casefold(), 0), reverse=True)
                result = {
                    "kind": "ranked_priorities",
                    "title": "Priorities ranked",
                    "summary": f"LifeOS ranked {len(priorities)} current priorit{'y' if len(priorities) == 1 else 'ies'} from verified workspace state.",
                    "priorities": priorities[:5],
                    "priority_count": len(priorities),
                    "reused_previous_step": reused_previous_step,
                    "verified_from_state": True,
                    "read_only": True,
                }

            elif capability == "intelligence.what_changed":
                activity = build_owned_recent_activity(owner_id=owner_id, query="What changed this week?", project_id=state.get("project_id"))
                result = {
                    "kind": "what_changed",
                    "title": "Recent changes reviewed",
                    "summary": activity.summary,
                    "items": activity.to_dict().get("items", [])[:8],
                    "activity_count": len(activity.to_dict().get("items", []) or []),
                    "verified_from_state": True,
                    "read_only": True,
                }

            elif capability == "intelligence.ask_lifeos":
                instruction = " ".join(str(config.get("instruction") or "").split())
                if len(instruction) < 3:
                    raise ValueError("Ask LifeOS needs an instruction before the flow can run.")
                selected_context = _selected_context_from_state(state)
                prior_summary = str(previous_result.get("summary") or previous_result.get("answer") or "").strip()
                query = instruction
                if prior_summary:
                    query += f"\n\nPrevious verified automation step summary: {prior_summary[:1200]}"

                fast_project_result = None
                if (
                    state.get("project_id") is not None
                    and isinstance(selected_context, dict)
                    and selected_context.get("type") == "project"
                ):
                    fast_project_result = _fast_project_custom_answer(
                        owner_id=owner_id,
                        project_id=int(state["project_id"]),
                        instruction=instruction,
                    )

                if fast_project_result is not None:
                    result = fast_project_result
                else:
                    asked = ask_lifeos(
                        query=query,
                        owner_id=owner_id,
                        selected_context=selected_context,
                        verification_policy="automation_fast",
                    )
                    payload = asked.to_dict(include_diagnostics=False)
                    result = {
                        "kind": "custom_ask_lifeos",
                        "title": "LifeOS answered the automation question",
                        "summary": str(payload.get("answer") or payload.get("clarification") or "LifeOS could not produce a verified answer."),
                        "answer": payload.get("answer"),
                        "attention_level": payload.get("attention_level"),
                        "verification": payload.get("verification"),
                        "grounded": payload.get("grounded"),
                        "response_mode": payload.get("response_mode"),
                        "verified_from_state": True,
                        "read_only": True,
                    }

            elif capability == "condition.attention_needed":
                minimum = str(config.get("minimum_attention") or "medium").casefold()
                threshold = {"medium": 2, "high": 3, "critical": 4}.get(minimum, 2)
                actual = _attention_value(previous_result)
                passed = actual >= threshold
                result = _gate_result(
                    passed=passed,
                    label="Attention gate passed" if passed else "No action needed",
                    reason=(
                        f"The previous result met the {minimum} attention threshold, so LifeOS continued."
                        if passed else
                        f"The previous result did not reach the {minimum} attention threshold, so LifeOS ended this run quietly."
                    ),
                    previous=previous_result,
                )

            elif capability == "condition.results_found":
                passed = _result_has_content(previous_result)
                result = _gate_result(
                    passed=passed,
                    label="Results gate passed" if passed else "Nothing actionable found",
                    reason=(
                        "The previous verified step produced results, so LifeOS continued."
                        if passed else
                        "The previous verified step produced no usable results, so LifeOS ended this run quietly."
                    ),
                    previous=previous_result,
                )

            elif capability == "output.notify_me":
                previous = state.get("result") if isinstance(state.get("result"), dict) else {}
                result = dict(previous)
                result["notification"] = _notification_from_result(previous, automation)
                result.setdefault("kind", "visual_flow_result")
                result.setdefault("title", f"{automation.name} completed")
                result.setdefault("summary", "LifeOS completed this visual intelligence flow from verified state.")

            elif capability == "output.save_review_result":
                previous = state.get("result") if isinstance(state.get("result"), dict) else {}
                result = dict(previous)
                result["saved_to_automation_run"] = True
                result.setdefault("summary", "The verified review result is preserved in this automation run history.")

            elif capability == "output.suggest_action":
                previous = state.get("result") if isinstance(state.get("result"), dict) else {}
                priorities = list(previous.get("priorities") or [])
                suggestion = priorities[0] if priorities else _priority_from_current_result_for_note(state=state, result=previous)
                state["suggestion"] = suggestion
                result = dict(previous)
                result["suggestion"] = suggestion
                result["requires_confirmation_for_mutation"] = True
                if suggestion is None:
                    result["suggestion_message"] = "The current verified result does not contain a safe workspace action to propose."

            elif capability in {"proposal.create_task", "proposal.save_note", "proposal.refresh_analysis"}:
                action_type = {
                    "proposal.create_task": ACTION_CREATE_TASK,
                    "proposal.save_note": ACTION_CREATE_NOTE,
                    "proposal.refresh_analysis": ACTION_REFRESH_DOCUMENT_ANALYSIS,
                }[capability]
                priority = state.get("suggestion")
                previous = state.get("result") if isinstance(state.get("result"), dict) else {}
                if not isinstance(priority, dict):
                    # Direct Intelligence -> Ask Me First flows consume the
                    # immediately preceding verified result. Do not silently
                    # substitute an unrelated workspace priority.
                    candidates = list(previous.get("priorities") or [])
                    if candidates and isinstance(candidates[0], dict):
                        priority = candidates[0]
                if action_type == ACTION_CREATE_NOTE and (not isinstance(priority, dict) or action_type not in {item["type"] for item in priority_action_options(priority)}):
                    priority = _priority_from_current_result_for_note(state=state, result=previous)
                if isinstance(priority, dict) and action_type not in {item["type"] for item in priority_action_options(priority)}:
                    priority = None
                if priority is None:
                    result = {
                        "kind": "i9_proposal",
                        "summary": "LifeOS did not find a verified priority compatible with this proposal node, so no action proposal was created.",
                        "proposal": None,
                        "requires_confirmation": True,
                        "workspace_mutation": False,
                    }
                elif dry_run:
                    result = {
                        "kind": "i9_proposal_preview",
                        "summary": f"Preview only: LifeOS would propose {action_type.replace('_', ' ')} for {priority.get('title') or 'the selected priority'}.",
                        "proposal": {"action_type": action_type, "status": "preview", "project_id": priority.get("project_id"), "requires_confirmation": True},
                        "workspace_mutation": False,
                    }
                else:
                    existing = _pending_matching_proposal(owner_id=owner_id, action_type=action_type, priority=priority)
                    proposal = existing or create_priority_action_proposal(owner_id=owner_id, action_type=action_type, priority=priority)
                    state["proposal"] = proposal_to_dict(proposal)
                    result = {
                        "kind": "i9_proposal",
                        "title": "LifeOS action proposal needs confirmation",
                        "summary": "LifeOS prepared a confirmation-gated action proposal. Nothing was changed in the workspace.",
                        "proposal": state["proposal"],
                        "workspace_mutation": False,
                        "requires_confirmation": True,
                        "notification": {
                            "should_notify": True,
                            "event_type": "automation.i9_proposal_ready",
                            "severity": "medium",
                            "title": "LifeOS action proposal needs confirmation",
                            "message": str(state["proposal"].get("title") or "Review the proposed LifeOS action before anything changes."),
                            "dedupe_scope": f"proposal:{state['proposal'].get('id')}",
                            "action_label": "Review proposal",
                            "action_href": "/ask",
                            "ask_query": "Show me the pending LifeOS action proposal and why it was suggested.",
                        },
                    }

            else:
                raise ValueError(f"Compiled capability is not executable: {capability}")

            state["step_results"][node_id] = result
            state["last_node_id"] = node_id
            trace_item["status"] = "succeeded"
            trace_item["result"] = _compact(result)

            if capability.startswith("condition."):
                # A passing gate controls execution but does not replace the
                # verified intelligence result that later Output/Proposal steps
                # should consume. A failing gate becomes the final run result.
                if result.get("continue_flow") is False:
                    state["result"] = result
                    state["halted"] = True
                    state["halt_reason"] = str(result.get("summary") or "The automation condition stopped this run.")
                else:
                    state["result"] = previous_result
            else:
                state["result"] = result

            if capability.startswith("condition.") and result.get("continue_flow") is False:
                for skipped in plan_steps[step_index + 1:]:
                    trace.append({
                        "index": int(skipped.get("index") or 0),
                        "node_id": str(skipped.get("node_id") or ""),
                        "node_type": str(skipped.get("node_type") or ""),
                        "label": str(skipped.get("label") or skipped.get("capability") or "Skipped step"),
                        "capability": str(skipped.get("capability") or ""),
                        "service_boundary": str(skipped.get("service_boundary") or ""),
                        "status": "skipped",
                        "skip_reason": "A previous condition ended the flow.",
                        "input_from_node_id": node_id,
                        "started_at": datetime.utcnow().isoformat(),
                        "finished_at": datetime.utcnow().isoformat(),
                        "duration_ms": 0.0,
                    })
                break
        except Exception as error:
            trace_item["status"] = "failed"
            trace_item["error"] = " ".join(str(error).split())[:1200]
            trace_item["finished_at"] = datetime.utcnow().isoformat()
            trace_item["duration_ms"] = round((perf_counter() - tick) * 1000, 2)
            raise AutomationFlowExecutionError(str(error), trace=trace, failed_node_id=node_id) from error
        finally:
            if trace_item.get("status") != "failed":
                trace_item["finished_at"] = datetime.utcnow().isoformat()
                trace_item["duration_ms"] = round((perf_counter() - tick) * 1000, 2)

    final_result = state.get("result") if isinstance(state.get("result"), dict) else {}
    output = dict(final_result)
    output.setdefault("kind", "compiled_visual_flow")
    output.setdefault("title", f"{automation.name} completed")
    output.setdefault("summary", "LifeOS completed the compiled visual intelligence flow.")
    output["compiled_plan_id"] = compiled_plan.get("plan_id")
    output["flow_trace"] = trace
    output["node_status"] = {item["node_id"]: item["status"] for item in trace}
    output["verified_from_state"] = True
    output["workspace_mutation"] = False
    output["dry_run"] = bool(dry_run)
    output["flow_halted"] = bool(state.get("halted"))
    output["halt_reason"] = state.get("halt_reason")
    if state.get("proposal") is not None:
        output["proposal"] = state["proposal"]
    return output

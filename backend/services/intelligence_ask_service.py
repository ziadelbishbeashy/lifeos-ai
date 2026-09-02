"""Product-level Ask LifeOS orchestration for the first verified AI workflow."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from services.intelligence_claim_verifier_service import (
    IntelligenceVerificationProviderError,
    IntelligenceVerificationResult,
    deterministic_verify_reasoning,
    verify_project_reasoning,
)
from services.intelligence_context_service import collect_owned_project_context
from services.intelligence_intent_router_service import (
    IntelligenceRouteDecision,
    route_intelligence_request,
)
from services.intelligence_reasoning_service import (
    IntelligenceReasoningError,
    reason_about_project_review,
)
from services.project_review_intelligence_service import ProjectReviewResult, review_project_context
from services.portfolio_review_intelligence_service import (
    build_deterministic_portfolio_answer,
    review_owned_portfolio,
)
from services.project_review_agent_service import (
    build_portfolio_agent_answer,
    build_project_agent_answer,
    review_project_with_agent,
    run_owned_portfolio_review_agent,
)
from services.intelligence_action_service import priority_action_options
from services.lifeos_activity_service import build_owned_recent_activity
from services.context_connection_service import ContextConnectionsResult, query_owned_context_connections
from services.structured_memory_service import build_owned_memory_summary
from services.ask_context_picker_service import AskContextOption, validate_owned_ask_context
from services.conversation_memory_service import propose_conversation_memory
from services.document_question_workflow_service import (
    DocumentQuestionWorkflowError,
    ask_owned_document,
)
from services.document_collection_question_workflow_service import (
    CollectionQuestionWorkflowError,
    ask_owned_collection_documents,
)
from services.module_question_workflow_service import (
    ModuleQuestionWorkflowError,
    ask_owned_module_documents,
)

from services.agent_planner_service import AgentPlannerError, plan_owned_agent_goal

from services.intelligence_workspace_query_service import (
    WorkspaceInsightResult,
    build_owned_deadline_insight,
    build_owned_document_review_insight,
    build_owned_project_question_insight,
    build_owned_study_next_insight,
    build_owned_task_status_insight,
    build_owned_today_focus_insight,
    build_owned_workspace_gaps_insight,
)


@dataclass(frozen=True)
class AskLifeOSResult:
    route: IntelligenceRouteDecision
    status: str
    answer: str | None
    response_mode: str
    verification: dict[str, Any] | None
    attention_level: str | None
    clarification: str | None
    agent: dict[str, Any] | None = None
    activity: dict[str, Any] | None = None
    insight: dict[str, Any] | None = None
    connections: dict[str, Any] | None = None
    memory: dict[str, Any] | None = None
    grounded: dict[str, Any] | None = None
    memory_suggestion: dict[str, Any] | None = None
    goal_plan: dict[str, Any] | None = None

    def to_dict(self, *, include_diagnostics: bool = False) -> dict[str, Any]:
        route_payload = self.route.to_dict() if include_diagnostics else {
            "intent": self.route.intent,
            "scope": (
                {
                    "type": self.route.scope_type,
                    "id": self.route.scope_id,
                    "label": self.route.scope_label,
                }
                if self.route.scope_type and self.route.scope_label
                else None
            ),
            "requires_clarification": self.route.requires_clarification,
            "candidates": (
                [item.to_dict() for item in self.route.candidates]
                if self.route.requires_clarification
                else []
            ),
        }
        verification = self.verification
        if verification is not None and not include_diagnostics:
            verification = {
                key: value
                for key, value in verification.items()
                if key != "issues"
            }
        return {
            "route": route_payload,
            "status": self.status,
            "answer": self.answer,
            "response_mode": self.response_mode,
            "verification": verification,
            "attention_level": self.attention_level,
            "clarification": self.clarification,
            "agent": self.agent,
            "activity": self.activity,
            "insight": self.insight,
            "connections": self.connections,
            "memory": self.memory,
            "grounded": self.grounded,
            "memory_suggestion": self.memory_suggestion,
            "goal_plan": self.goal_plan,
            "read_only": True,
        }


def _fact_lookup(review: ProjectReviewResult) -> dict[str, Any]:
    return {str(item.get("key")): item.get("value") for item in review.facts}


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or singular + "s")


def build_deterministic_project_answer(review: ProjectReviewResult) -> str:
    """Trusted fallback used whenever model reasoning cannot be fully verified."""

    facts = _fact_lookup(review)
    title = str(facts.get("project.title") or review.project.get("title") or "This project")
    status = str(facts.get("project.status") or "").strip()
    manual_progress = int(facts.get("project.manual_progress") or 0)
    total = int(facts.get("project.total_tasks") or 0)
    completed = int(facts.get("project.completed_tasks") or 0)
    overdue = int(facts.get("project.overdue_tasks") or 0)
    blocked = int(facts.get("project.blocked_tasks") or 0)
    due_soon = int(facts.get("project.due_soon_tasks") or 0)
    documents = int(facts.get("project.current_documents") or 0)
    stale = int(facts.get("project.stale_document_analyses") or 0)

    opening = f"{title}"
    if status:
        opening += f" is currently {status}."
    else:
        opening += "."
    opening += f" Its saved project progress is {manual_progress}%."

    if total:
        task_text = (
            f" It has {total} {_plural(total, 'task')}: {completed} completed, "
            f"{overdue} overdue, {blocked} blocked, and {due_soon} due soon."
        )
    else:
        task_text = " It currently has no project tasks to measure task completion from."

    document_text = f" There {_plural(documents, 'is', 'are')} {documents} current {_plural(documents, 'document')} linked to the project."
    if stale:
        document_text += f" {stale} {_plural(stale, 'document analysis', 'document analyses')} {_plural(stale, 'is', 'are')} stale and should not be relied on as current intelligence."

    attention = ""
    if review.signals:
        attention = " Main attention: " + "; ".join(item.title for item in review.signals[:2]) + "."
    recommendation = ""
    if review.suggestions:
        recommendation = " Recommendation: " + review.suggestions[0].detail

    return "".join((opening, task_text, document_text, attention, recommendation)).strip()


def _fallback_verification(reason: str) -> dict[str, Any]:
    return {
        "status": "trusted_fallback",
        "deterministic_checks_passed": True,
        "prose_check_performed": False,
        "issues": [reason],
        "checked_claims": {"factual": 0, "inference": 0, "recommendation": 0},
    }


def _agent_payload_with_actions(payload: dict[str, Any]) -> dict[str, Any]:
    """Expose only reviewed I9 action choices for each deterministic priority."""

    result = dict(payload)
    priorities = []
    for raw in list(payload.get("priorities") or []):
        item = dict(raw)
        item["actions"] = priority_action_options(item)
        priorities.append(item)
    result["priorities"] = priorities
    return result



def _verified_insight_response(
    *,
    route: IntelligenceRouteDecision,
    insight: WorkspaceInsightResult,
    attention_level: str | None = None,
) -> AskLifeOSResult:
    return AskLifeOSResult(
        route=route,
        status="completed",
        answer=insight.summary,
        response_mode="deterministic_verified",
        verification={
            "status": "verified",
            "deterministic_checks_passed": True,
            "prose_check_performed": False,
            "checked_claims": {
                "factual": len(insight.items),
                "inference": 0,
                "recommendation": sum(1 for item in insight.items if item.action_hint),
            },
        },
        attention_level=attention_level,
        clarification=None,
        insight=insight.to_dict(),
    )



def _route_for_selected_context(*, query: str, context: AskContextOption, intent: str) -> IntelligenceRouteDecision:
    return IntelligenceRouteDecision(
        query=query,
        intent=intent,
        confidence=1.0,
        scope_type=context.type,
        scope_id=context.id,
        scope_label=context.label,
        status="ready",
        requires_clarification=False,
        clarification=None,
        candidates=(),
        router_version="deterministic-router-v1+explicit-context",
    )


def _grounded_payload(*, context: AskContextOption, answer: str, sources: list[Any], reused: bool, question_id: int) -> dict[str, Any]:
    return {
        "kind": f"{context.type}_rag",
        "scope": context.to_dict(),
        "answer": answer,
        "sources": list(sources or []),
        "source_count": len(list(sources or [])),
        "question_id": int(question_id),
        "reused_existing": bool(reused),
        "verified_grounding": True,
    }


def _answer_selected_knowledge_context(*, query: str, owner_id: int, context: AskContextOption) -> AskLifeOSResult | None:
    """Route an explicit Document/Collection/Module/Lecture chip to the existing RAG pipeline."""

    try:
        if context.type == "document":
            saved = ask_owned_document(
                document_id=context.id,
                user_id=owner_id,
                question_text=query,
            )
            row = saved.question
            route = _route_for_selected_context(query=query, context=context, intent="document_question")
        elif context.type == "collection":
            saved = ask_owned_collection_documents(
                collection_id=context.id,
                user_id=owner_id,
                question_text=query,
            )
            row = saved.question
            route = _route_for_selected_context(query=query, context=context, intent="collection_question")
        elif context.type in {"module", "lecture"}:
            module_id = context.id if context.type == "module" else int(context.parent_id or 0)
            lecture_id = context.id if context.type == "lecture" else None
            saved = ask_owned_module_documents(
                module_id=module_id,
                lecture_id=lecture_id,
                user_id=owner_id,
                question_text=query,
            )
            row = saved.question
            route = _route_for_selected_context(
                query=query,
                context=context,
                intent="lecture_question" if context.type == "lecture" else "module_question",
            )
        else:
            return None
    except (DocumentQuestionWorkflowError, CollectionQuestionWorkflowError, ModuleQuestionWorkflowError) as error:
        route = _route_for_selected_context(query=query, context=context, intent=f"{context.type}_question")
        return AskLifeOSResult(
            route=route,
            status="completed",
            answer=str(error),
            response_mode="deterministic_fallback",
            verification=_fallback_verification("Selected context could not produce a grounded answer."),
            attention_level=None,
            clarification=None,
            grounded={
                "kind": f"{context.type}_rag",
                "scope": context.to_dict(),
                "answer": str(error),
                "sources": [],
                "source_count": 0,
                "verified_grounding": False,
            },
        )

    answer = str(row.answer or "").strip()
    sources = list(getattr(row, "sources", []) or [])
    payload = _grounded_payload(
        context=context,
        answer=answer,
        sources=sources,
        reused=bool(saved.reused_existing),
        question_id=int(row.id),
    )
    return AskLifeOSResult(
        route=route,
        status="completed",
        answer=answer,
        response_mode="grounded_rag_verified",
        verification={
            "status": "verified",
            "deterministic_checks_passed": True,
            "prose_check_performed": True,
            "checked_claims": {
                "factual": len(sources),
                "inference": 0,
                "recommendation": 0,
            },
        },
        attention_level=None,
        clarification=None,
        grounded=payload,
    )


def _looks_like_goal_request(query: str) -> bool:
    """Recognize requests that benefit from the bounded I19 goal runtime.

    This is intentionally conservative.  Simple questions continue through the
    existing Ask LifeOS / RAG / deterministic routes; only clearly goal-shaped
    requests are offered a multi-step review plan.
    """

    text = " ".join(str(query or "").casefold().split())
    if len(text) < 12:
        return False
    strong_starts = (
        "help me ",
        "help us ",
        "prepare me ",
        "prepare this ",
        "prepare my ",
        "get me ready ",
        "get this ready ",
        "get my ",
        "make this ready ",
        "make my ",
        "plan how ",
        "figure out what i need ",
        "figure out what we need ",
    )
    if text.startswith(strong_starts):
        return True
    phrases = (
        "get this project ready",
        "get the project ready",
        "ready for deployment",
        "ready for launch",
        "ready to deploy",
        "ready to launch",
        "what do i need to do to finish",
        "what do we need to do to finish",
        "what do i need to do to launch",
        "what do i need to do to deploy",
        "what should i do next to",
        "what should we do next to",
        "what should i focus on to",
        "review everything needed",
        "identify the biggest blockers",
        "tell me the blockers and what to do",
        "move this project forward",
        "move the project forward",
        "reach this goal",
        "achieve this goal",
    )
    if any(phrase in text for phrase in phrases):
        return True

    # Multi-part objective requests are goal shaped even when they do not use a
    # canned phrase. Requiring at least two signals keeps simple questions such
    # as "what is the biggest risk?" on the existing fast review path.
    # Count semantic signal groups, not raw substrings.  A word such as
    # "deployment" also contains "deploy"; counting both made ordinary file
    # questions such as "Which tasks came from Deployment_Plan.pdf?" look like
    # multi-step goals.
    goal_signal_groups = (
        ("blocker", "blockers"),
        ("risk", "risks"),
        ("focus",),
        ("next action", "next step"),
        ("what to do",),
        ("move forward",),
        ("ready", "prepare"),
        ("deployment", "deploy"),
        ("launch",),
        ("finish", "complete"),
    )
    score = sum(1 for group in goal_signal_groups if any(signal in text for signal in group))
    return score >= 2


def _goal_plan_context(explicit_context: AskContextOption | None, route: IntelligenceRouteDecision) -> dict[str, Any] | None:
    if explicit_context is not None:
        if explicit_context.type == "project":
            return {"type": "project", "id": int(explicit_context.id)}
        return None
    if route.scope_type == "project" and route.scope_id is not None:
        return {"type": "project", "id": int(route.scope_id)}
    return None


def ask_lifeos(
    *,
    query: str,
    owner_id: int,
    clarification_context: dict[str, Any] | None = None,
    selected_context: dict[str, Any] | None = None,
    verification_policy: str = "full",
) -> AskLifeOSResult:
    """Route and answer verified workflows, preserving safe clarification context."""

    explicit_context = validate_owned_ask_context(owner_id=owner_id, raw_context=selected_context)

    continuation_intent = None
    if isinstance(clarification_context, dict):
        candidate = str(clarification_context.get("intent") or "").strip()
        if candidate in {
            "project_review", "project_focus", "recent_activity", "task_status",
            "deadline_review", "document_review", "workspace_gaps", "project_question", "today_focus",
        }:
            continuation_intent = candidate

    route = route_intelligence_request(
        query=query,
        owner_id=owner_id,
        continuation_intent=continuation_intent,
        forced_project_id=(explicit_context.id if explicit_context and explicit_context.type == "project" else None),
    )

    # The visible project chip is an explicit user scope and therefore wins over
    # broad wording such as "all projects" until the user clears the chip.
    if explicit_context is not None and explicit_context.type == "project":
        selected_intent = (
            "project_focus" if route.intent == "portfolio_focus"
            else "project_review" if route.intent == "portfolio_review"
            else route.intent
        )
        route = replace(
            route,
            intent=selected_intent,
            scope_type="project",
            scope_id=explicit_context.id,
            scope_label=explicit_context.label,
            requires_clarification=False,
            clarification=None,
            candidates=(),
            status="ready",
        )

    # Preserve the visible selected chip on memory proposals/queries without
    # letting a Document/Module selection bypass their dedicated knowledge flow.
    if explicit_context is not None and route.intent in {"memory_candidate", "memory_query"}:
        route = replace(
            route,
            scope_type=explicit_context.type,
            scope_id=explicit_context.id,
            scope_label=explicit_context.label,
            requires_clarification=False,
            clarification=None,
            candidates=(),
            status="ready",
        )

    if route.intent == "memory_candidate":
        suggestion = propose_conversation_memory(text=query, selected_context=explicit_context)
        if suggestion is not None:
            return AskLifeOSResult(
                route=route,
                status="memory_confirmation_required",
                answer="I can remember that as structured LifeOS memory for future conversations. I will save it only if you confirm.",
                response_mode="memory_proposal",
                verification={
                    "status": "verified",
                    "deterministic_checks_passed": True,
                    "prose_check_performed": False,
                    "checked_claims": {"factual": 0, "inference": 0, "recommendation": 1},
                },
                attention_level=None,
                clarification=None,
                memory_suggestion=suggestion.to_dict(),
            )

    if explicit_context is not None and explicit_context.type in {"document", "collection", "module", "lecture"}:
        scoped = _answer_selected_knowledge_context(query=query, owner_id=owner_id, context=explicit_context)
        if scoped is not None:
            return scoped
    if route.requires_clarification:
        return AskLifeOSResult(
            route=route,
            status="clarification_required",
            answer=None,
            response_mode="clarification",
            verification=None,
            attention_level=None,
            clarification=route.clarification,
        )

    # Specific deterministic routes must be resolved before I19 goal planning.
    # I19 is an enhancement layer, never a replacement for provenance, status,
    # deadline, activity, or other routes that already have an authoritative
    # deterministic answer path.  Keeping context-connections here is especially
    # important because document filenames may contain goal-like words such as
    # "deployment".
    if route.intent == "context_connections":
        connections = query_owned_context_connections(owner_id=owner_id, query=query)
        return AskLifeOSResult(
            route=route,
            status="completed",
            answer=connections.summary,
            response_mode="deterministic_verified",
            verification={
                "status": "verified",
                "deterministic_checks_passed": True,
                "prose_check_performed": False,
                "checked_claims": {
                    "factual": len(connections.connections),
                    "inference": 0,
                    "recommendation": 0,
                },
            },
            attention_level=None,
            clarification=None,
            connections=connections.to_dict(),
        )

    # I19 is a hidden capability of Ask LifeOS, not a separate user-facing
    # module.  Clear goal-shaped requests get a bounded read-only plan first;
    # nothing executes until the user explicitly starts the review in chat.
    # I19 may enrich broad review/goal requests, but it must never override a
    # more specific deterministic route that already knows exactly how to
    # answer the question.  In particular, I13 provenance/context-connection
    # questions must stay deterministic even when a filename contains words
    # such as "deployment".
    goal_blocked_intents = {
        "memory_query",
        "context_connections",
    }
    goal_shaped = _looks_like_goal_request(query)
    explicit_project_goal = bool(
        goal_shaped
        and explicit_context is not None
        and explicit_context.type == "project"
    )
    broad_goal = bool(
        goal_shaped
        and explicit_context is None
        and route.intent not in {
            "today_focus",
            "task_status",
            "deadline_review",
            "document_review",
            "study_next",
            "project_question",
            "recent_activity",
        }
    )
    if (
        route.intent not in goal_blocked_intents
        and (explicit_project_goal or broad_goal)
    ):
        try:
            goal_plan = plan_owned_agent_goal(
                owner_id=owner_id,
                goal=query,
                selected_context=_goal_plan_context(explicit_context, route),
            )
        except AgentPlannerError:
            goal_plan = None
        if goal_plan is not None:
            plan_payload = goal_plan.to_dict()
            route = replace(
                route,
                scope_type=goal_plan.scope.type,
                scope_id=goal_plan.scope.id,
                scope_label=goal_plan.scope.label,
                requires_clarification=False,
                clarification=None,
                candidates=(),
                status="ready",
            )
            return AskLifeOSResult(
                route=route,
                status="goal_plan_ready",
                answer="This needs a few trusted LifeOS checks. I prepared a read-only review plan below; nothing has run yet.",
                response_mode="goal_plan",
                verification={
                    "status": "verified",
                    "deterministic_checks_passed": True,
                    "prose_check_performed": False,
                    "checked_claims": {"factual": 0, "inference": 0, "recommendation": 1},
                },
                attention_level=None,
                clarification=None,
                goal_plan=plan_payload,
            )

    project_scope_id = route.scope_id if route.scope_type == "project" else None

    if route.intent == "memory_query":
        memory = build_owned_memory_summary(owner_id=owner_id, query=query)
        return AskLifeOSResult(
            route=route,
            status="completed",
            answer=memory["summary"],
            response_mode="deterministic_verified",
            verification={
                "status": "verified",
                "deterministic_checks_passed": True,
                "prose_check_performed": False,
                "checked_claims": {
                    "factual": len(memory["items"]),
                    "inference": 0,
                    "recommendation": 0,
                },
            },
            attention_level=None,
            clarification=None,
            memory=memory,
        )

    if route.intent == "today_focus":
        insight = build_owned_today_focus_insight(owner_id=owner_id, project_id=project_scope_id)
        return _verified_insight_response(route=route, insight=insight)

    if route.intent == "task_status":
        insight = build_owned_task_status_insight(
            owner_id=owner_id,
            query=query,
            project_id=project_scope_id,
        )
        return _verified_insight_response(route=route, insight=insight)

    if route.intent == "deadline_review":
        insight = build_owned_deadline_insight(
            owner_id=owner_id,
            query=query,
            project_id=project_scope_id,
        )
        return _verified_insight_response(route=route, insight=insight)

    if route.intent == "document_review":
        insight = build_owned_document_review_insight(
            owner_id=owner_id,
            project_id=project_scope_id,
        )
        return _verified_insight_response(route=route, insight=insight)

    if route.intent == "workspace_gaps":
        insight = build_owned_workspace_gaps_insight(
            owner_id=owner_id,
            project_id=project_scope_id,
        )
        return _verified_insight_response(route=route, insight=insight)

    if route.intent == "study_next":
        insight = build_owned_study_next_insight(owner_id=owner_id)
        return _verified_insight_response(route=route, insight=insight)

    if route.intent == "project_question" and route.scope_type == "project" and route.scope_id:
        insight = build_owned_project_question_insight(
            owner_id=owner_id,
            project_id=route.scope_id,
            query=query,
        )
        return _verified_insight_response(route=route, insight=insight)

    if route.intent == "recent_activity":
        activity = build_owned_recent_activity(
            owner_id=owner_id,
            query=query,
            project_id=(route.scope_id if route.scope_type == "project" else None),
        )
        return AskLifeOSResult(
            route=route,
            status="completed",
            answer=activity.summary,
            response_mode="deterministic_verified",
            verification={
                "status": "verified",
                "deterministic_checks_passed": True,
                "prose_check_performed": False,
                "checked_claims": {
                    "factual": len(activity.items),
                    "inference": 0,
                    "recommendation": 0,
                },
            },
            attention_level=None,
            clarification=None,
            activity=activity.to_dict(),
        )

    if route.intent == "portfolio_focus":
        agent = run_owned_portfolio_review_agent(owner_id=owner_id)
        return AskLifeOSResult(
            route=route,
            status="completed",
            answer=build_portfolio_agent_answer(agent),
            response_mode="agent_verified",
            verification={
                "status": "verified",
                "deterministic_checks_passed": True,
                "prose_check_performed": False,
                "checked_claims": {
                    "factual": len(agent.priorities),
                    "inference": 0,
                    "recommendation": len(agent.priorities),
                },
            },
            attention_level=agent.attention_level,
            clarification=None,
            agent=_agent_payload_with_actions(agent.to_dict()),
        )

    if route.intent == "portfolio_review":
        portfolio = review_owned_portfolio(owner_id=owner_id)
        return AskLifeOSResult(
            route=route,
            status="completed",
            answer=build_deterministic_portfolio_answer(portfolio),
            response_mode="deterministic_verified",
            verification={
                "status": "verified",
                "deterministic_checks_passed": True,
                "prose_check_performed": False,
                "checked_claims": {
                    "factual": portfolio.reviewed_projects,
                    "inference": 0,
                    "recommendation": 0,
                },
            },
            attention_level=portfolio.attention_level,
            clarification=None,
        )

    if route.intent == "project_focus" and route.scope_type == "project" and route.scope_id:
        context = collect_owned_project_context(project_id=route.scope_id, owner_id=owner_id)
        review = review_project_context(context=context)
        agent = review_project_with_agent(context=context, review=review)
        return AskLifeOSResult(
            route=route,
            status="completed",
            answer=build_project_agent_answer(agent),
            response_mode="agent_verified",
            verification={
                "status": "verified",
                "deterministic_checks_passed": True,
                "prose_check_performed": False,
                "checked_claims": {
                    "factual": len(agent.priorities),
                    "inference": 0,
                    "recommendation": len(agent.priorities),
                },
            },
            attention_level=agent.attention_level,
            clarification=None,
            agent=_agent_payload_with_actions(agent.to_dict()),
        )

    if not (route.intent == "project_review" and route.scope_type == "project" and route.scope_id):
        return AskLifeOSResult(
            route=route,
            status="unsupported_intent",
            answer=None,
            response_mode="route_only",
            verification=None,
            attention_level=None,
            clarification="This Ask LifeOS intent is recognized but does not have a verified executor yet.",
        )

    # Gather the reviewed tool/context state once, then derive the deterministic
    # review from that same packet. This avoids duplicate DB/tool work per Ask LifeOS
    # request and guarantees the reasoner/reviewer see the same snapshot.
    context = collect_owned_project_context(project_id=route.scope_id, owner_id=owner_id)
    review = review_project_context(context=context)
    fallback = build_deterministic_project_answer(review)

    try:
        reasoning = reason_about_project_review(query=query, context=context, review=review)
    except IntelligenceReasoningError as error:
        return AskLifeOSResult(
            route=route,
            status="completed",
            answer=fallback,
            response_mode="deterministic_fallback",
            verification=_fallback_verification("AI reasoning was unavailable; LifeOS used verified project state instead."),
            attention_level=review.attention_level,
            clarification=None,
        )

    if verification_policy == "automation_fast":
        # I18 custom-question automations already run inside a constrained, read-only
        # capability boundary and any workspace mutation still stops at I9.  Avoid a
        # second provider round-trip here: verify the model's structured fact/support
        # bindings deterministically against the same trusted project snapshot.
        deterministic_ok, deterministic_issues = deterministic_verify_reasoning(
            reasoning=reasoning,
            context=context,
            review=review,
        )
        verification = IntelligenceVerificationResult(
            verified=deterministic_ok,
            deterministic_checks_passed=deterministic_ok,
            prose_check_performed=False,
            issues=deterministic_issues,
            checked_factual_claims=len(reasoning.factual_claims),
            checked_inferences=len(reasoning.inferences),
            checked_recommendations=len(reasoning.recommendations),
        )
    elif verification_policy == "full":
        try:
            verification = verify_project_reasoning(
                query=query,
                reasoning=reasoning,
                context=context,
                review=review,
            )
        except IntelligenceVerificationProviderError as error:
            return AskLifeOSResult(
                route=route,
                status="completed",
                answer=fallback,
                response_mode="deterministic_fallback",
                verification=_fallback_verification("AI verification was unavailable; LifeOS used verified project state instead."),
                attention_level=review.attention_level,
                clarification=None,
            )
    else:
        raise ValueError("Unsupported Ask LifeOS verification policy.")

    if not verification.verified:
        return AskLifeOSResult(
            route=route,
            status="completed",
            answer=fallback,
            response_mode="deterministic_fallback",
            verification=verification.to_dict(),
            attention_level=review.attention_level,
            clarification=None,
        )

    verification_payload = verification.to_dict()
    if verification_policy == "automation_fast":
        verification_payload["policy"] = "automation_fast"

    return AskLifeOSResult(
        route=route,
        status="completed",
        answer=reasoning.answer,
        response_mode=("ai_verified_fast" if verification_policy == "automation_fast" else "ai_verified"),
        verification=verification_payload,
        attention_level=review.attention_level,
        clarification=None,
    )

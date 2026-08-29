"""I2/I3 orchestration boundary: route first, execute only reviewed workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.intelligence_intent_router_service import (
    IntelligenceRouteDecision,
    route_intelligence_request,
)
from services.project_review_intelligence_service import review_owned_project
from services.lifeos_activity_service import build_owned_recent_activity
from services.context_connection_service import query_owned_context_connections
from services.project_review_agent_service import (
    run_owned_portfolio_review_agent,
    run_owned_project_review_agent,
)
from services.intelligence_workspace_query_service import (
    build_owned_deadline_insight,
    build_owned_document_review_insight,
    build_owned_project_question_insight,
    build_owned_study_next_insight,
    build_owned_task_status_insight,
    build_owned_today_focus_insight,
    build_owned_workspace_gaps_insight,
)


@dataclass(frozen=True)
class IntelligenceRequestResult:
    route: IntelligenceRouteDecision
    result_type: str
    result: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self.route.to_dict(),
            "result_type": self.result_type,
            "result": self.result,
            "read_only": True,
        }


def handle_intelligence_request(*, query: str, owner_id: int) -> IntelligenceRequestResult:
    """Route natural language and execute only explicitly reviewed read-only flows."""

    route = route_intelligence_request(query=query, owner_id=owner_id)
    if route.requires_clarification:
        return IntelligenceRequestResult(route, "clarification", None)

    if route.intent == "project_review" and route.scope_type == "project" and route.scope_id:
        review = review_owned_project(project_id=route.scope_id, owner_id=owner_id)
        return IntelligenceRequestResult(route, "project_review", review.to_dict())

    if route.intent == "project_focus" and route.scope_type == "project" and route.scope_id:
        agent = run_owned_project_review_agent(project_id=route.scope_id, owner_id=owner_id)
        return IntelligenceRequestResult(route, "project_review_agent", agent.to_dict())

    if route.intent == "portfolio_focus":
        agent = run_owned_portfolio_review_agent(owner_id=owner_id)
        return IntelligenceRequestResult(route, "portfolio_review_agent", agent.to_dict())

    if route.intent == "recent_activity":
        activity = build_owned_recent_activity(
            owner_id=owner_id,
            query=query,
            project_id=(route.scope_id if route.scope_type == "project" else None),
        )
        return IntelligenceRequestResult(route, "recent_activity", activity.to_dict())

    project_scope_id = route.scope_id if route.scope_type == "project" else None
    if route.intent == "context_connections":
        connections = query_owned_context_connections(owner_id=owner_id, query=query)
        return IntelligenceRequestResult(route, "context_connections", connections.to_dict())
    if route.intent == "today_focus":
        insight = build_owned_today_focus_insight(owner_id=owner_id, project_id=project_scope_id)
        return IntelligenceRequestResult(route, "workspace_insight", insight.to_dict())
    if route.intent == "task_status":
        insight = build_owned_task_status_insight(owner_id=owner_id, query=query, project_id=project_scope_id)
        return IntelligenceRequestResult(route, "workspace_insight", insight.to_dict())
    if route.intent == "deadline_review":
        insight = build_owned_deadline_insight(owner_id=owner_id, query=query, project_id=project_scope_id)
        return IntelligenceRequestResult(route, "workspace_insight", insight.to_dict())
    if route.intent == "document_review":
        insight = build_owned_document_review_insight(owner_id=owner_id, project_id=project_scope_id)
        return IntelligenceRequestResult(route, "workspace_insight", insight.to_dict())
    if route.intent == "workspace_gaps":
        insight = build_owned_workspace_gaps_insight(owner_id=owner_id, project_id=project_scope_id)
        return IntelligenceRequestResult(route, "workspace_insight", insight.to_dict())
    if route.intent == "study_next":
        insight = build_owned_study_next_insight(owner_id=owner_id)
        return IntelligenceRequestResult(route, "workspace_insight", insight.to_dict())
    if route.intent == "project_question" and route.scope_type == "project" and route.scope_id:
        insight = build_owned_project_question_insight(owner_id=owner_id, project_id=route.scope_id, query=query)
        return IntelligenceRequestResult(route, "workspace_insight", insight.to_dict())

    return IntelligenceRequestResult(route, "route_only", None)

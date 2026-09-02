"""Read-only API boundary for the LifeOS Intelligence Layer."""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user

from lifeos.api.v1.common import api_auth_required, json_body, not_found, validation_error
from services.intelligence_ask_service import ask_lifeos
from services.agent_planner_service import AgentPlannerError, plan_owned_agent_goal
from services.agent_runtime_service import (
    AgentProposalError,
    AgentRunNotFoundError,
    AgentRuntimeError,
    agent_run_to_dict,
    list_owned_agent_runs,
    prepare_agent_action_proposal,
    require_owned_agent_run,
    run_owned_agent_goal,
)
from services.intelligence_context_service import collect_owned_project_context
from services.intelligence_intent_router_service import IntelligenceRouterError
from services.intelligence_request_service import handle_intelligence_request
from services.project_review_intelligence_service import review_owned_project
from services.today_intelligence_service import build_owned_today_intelligence
from services.home_intelligence_service import build_owned_home_intelligence
from services.workspace_context_service import WorkspaceContextNotFoundError
from services.intelligence_action_service import (
    IntelligenceActionExecutionError,
    IntelligenceActionNotFoundError,
    IntelligenceActionValidationError,
    confirm_owned_action_proposal,
    create_priority_action_proposal,
    dismiss_owned_action_proposal,
    proposal_to_dict,
    require_owned_proposal,
)
from services.lifeos_activity_service import build_owned_recent_activity
from services.context_connection_service import (
    ContextConnectionNotFoundError,
    ContextConnectionValidationError,
    build_owned_context_connections,
)
from services.intelligence_event_service import (
    event_to_dict,
    list_owned_intelligence_events,
    scan_owned_intelligence_events,
)
from services.proactive_intelligence_service import (
    ProactiveNotificationNotFoundError,
    dismiss_owned_proactive_notification,
    list_owned_proactive_notifications,
    mark_all_owned_proactive_notifications_read,
    mark_owned_proactive_notification_read,
    notification_to_dict,
    refresh_owned_proactive_notifications,
)
from services.ask_context_picker_service import (
    AskContextNotFoundError,
    AskContextValidationError,
    list_owned_ask_context_options,
    validate_owned_ask_context,
)
from services.conversation_memory_service import propose_conversation_memory
from services.structured_memory_service import (
    StructuredMemoryNotFoundError,
    StructuredMemoryValidationError,
    clear_owned_memories,
    delete_owned_memory,
    list_owned_memories,
    memory_to_dict,
    refresh_owned_structured_memory,
    save_owned_user_memory,
)


intelligence_api_bp = Blueprint(
    "api_v1_intelligence",
    __name__,
    url_prefix="/api/v1/intelligence",
)


@intelligence_api_bp.post("/ask")
@api_auth_required
def ask_lifeos_route():
    """Return a natural answer only after I4/I5 verification or trusted fallback."""

    payload = json_body()
    try:
        result = ask_lifeos(
            query=payload.get("query") or "",
            owner_id=current_user.id,
            clarification_context=payload.get("clarification_context"),
            selected_context=payload.get("selected_context"),
        )
    except (IntelligenceRouterError, AskContextValidationError) as error:
        return validation_error(str(error))
    except (WorkspaceContextNotFoundError, AskContextNotFoundError):
        return not_found("The requested LifeOS scope was not found.")

    return jsonify(result.to_dict())


@intelligence_api_bp.get("/context-options")
@api_auth_required
def ask_context_options_route():
    """Return owner-validated resources available to the Ask LifeOS context picker."""

    return jsonify({"contexts": list_owned_ask_context_options(owner_id=current_user.id)})


@intelligence_api_bp.post("/goal-plan")
@api_auth_required
def goal_plan_route():
    """Plan a complex Ask LifeOS goal without executing any tool."""

    payload = json_body()
    try:
        plan = plan_owned_agent_goal(
            owner_id=current_user.id,
            goal=payload.get("goal"),
            selected_context=payload.get("selected_context"),
        )
    except (AgentPlannerError, AskContextValidationError) as error:
        return validation_error(str(error))
    except AskContextNotFoundError:
        return not_found("The selected LifeOS context was not found.")
    return jsonify({"plan": plan.to_dict()})


@intelligence_api_bp.post("/goal-runs")
@api_auth_required
def goal_run_route():
    """Execute one bounded, read-only goal review from Ask LifeOS."""

    payload = json_body()
    try:
        run = run_owned_agent_goal(
            owner_id=current_user.id,
            goal=payload.get("goal"),
            selected_context=payload.get("selected_context"),
        )
    except (AgentPlannerError, AskContextValidationError) as error:
        return validation_error(str(error))
    except AskContextNotFoundError:
        return not_found("The selected LifeOS context was not found.")
    except AgentRuntimeError as error:
        return jsonify({"error": "goal_review_failed", "message": str(error)}), 503
    return jsonify({"run": agent_run_to_dict(run)}), 201


@intelligence_api_bp.get("/goal-runs")
@api_auth_required
def goal_runs_route():
    raw_limit = request.args.get("limit", "12")
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return validation_error("Invalid goal review history limit.")
    return jsonify({"runs": list_owned_agent_runs(owner_id=current_user.id, limit=limit)})


@intelligence_api_bp.get("/goal-runs/<int:run_id>")
@api_auth_required
def goal_run_details_route(run_id: int):
    try:
        run = require_owned_agent_run(owner_id=current_user.id, run_id=run_id)
    except AgentRunNotFoundError:
        return not_found("Goal review not found.")
    return jsonify({"run": agent_run_to_dict(run)})


@intelligence_api_bp.post("/goal-runs/<int:run_id>/proposals")
@api_auth_required
def goal_prepare_proposal_route(run_id: int):
    """Prepare an I9 proposal from trusted goal-review output; never execute it."""

    payload = json_body()
    try:
        proposal = prepare_agent_action_proposal(
            owner_id=current_user.id,
            run_id=run_id,
            suggestion_id=str(payload.get("suggestion_id") or ""),
            action_type=str(payload.get("action_type") or ""),
        )
    except AgentRunNotFoundError:
        return not_found("Goal review not found.")
    except AgentProposalError as error:
        return validation_error(str(error))
    return jsonify({"proposal": proposal_to_dict(proposal)}), 201


@intelligence_api_bp.post("/memory/propose")
@api_auth_required
def memory_propose_route():
    """Prepare, but never persist, a conversational memory suggestion."""

    payload = json_body()
    try:
        context = validate_owned_ask_context(
            owner_id=current_user.id,
            raw_context=payload.get("selected_context"),
        )
    except AskContextValidationError as error:
        return validation_error(str(error))
    except AskContextNotFoundError:
        return not_found("The selected LifeOS context was not found.")

    suggestion = propose_conversation_memory(
        text=payload.get("text") or "",
        selected_context=context,
        force=True,
    )
    if suggestion is None:
        return jsonify({
            "suggestion": None,
            "message": "That message does not look like a reusable preference or current focus.",
        })
    return jsonify({"suggestion": suggestion.to_dict()})


@intelligence_api_bp.get("/today")
@api_auth_required
def today_intelligence_route():
    """Return the verified, read-only attention view used by LifeOS Home."""

    result = build_owned_today_intelligence(owner_id=current_user.id)
    return jsonify({"today": result.to_dict()})


@intelligence_api_bp.get("/home")
@api_auth_required
def home_intelligence_route():
    """Return the I12 verified Home packet; no LLM call or mutation occurs."""

    result = build_owned_home_intelligence(owner_id=current_user.id)
    return jsonify({"home": result.to_dict()})


@intelligence_api_bp.get("/projects/<int:project_id>/review")
@api_auth_required
def project_review_route(project_id: int):
    """Return a verified, read-only project attention review."""

    try:
        result = review_owned_project(
            project_id=project_id,
            owner_id=current_user.id,
        )
    except WorkspaceContextNotFoundError:
        return not_found("Project not found.")

    return jsonify({"review": result.to_dict()})


@intelligence_api_bp.get("/projects/<int:project_id>/context")
@api_auth_required
def project_context_route(project_id: int):
    """Expose the trusted I2 context packet without raw internal tool data."""

    try:
        context = collect_owned_project_context(
            project_id=project_id,
            owner_id=current_user.id,
        )
    except WorkspaceContextNotFoundError:
        return not_found("Project not found.")

    return jsonify({"context": context.to_dict(include_tool_data=False)})


@intelligence_api_bp.post("/route")
@api_auth_required
def route_intelligence_request_route():
    """Route natural language into reviewed LifeOS intelligence workflows."""

    payload = json_body()
    try:
        result = handle_intelligence_request(
            query=payload.get("query") or "",
            owner_id=current_user.id,
        )
    except IntelligenceRouterError as error:
        return validation_error(str(error))
    except WorkspaceContextNotFoundError:
        # Neutral failure even when a guessed/stale target ID was supplied.
        return not_found("The requested LifeOS scope was not found.")

    return jsonify(result.to_dict())


@intelligence_api_bp.post("/action-proposals")
@api_auth_required
def create_action_proposal_route():
    """Persist a pending I9 proposal. No workspace write happens here."""

    payload = json_body()
    priority = payload.get("priority")
    if not isinstance(priority, dict):
        return validation_error("A verified LifeOS priority is required.")
    try:
        proposal = create_priority_action_proposal(
            owner_id=current_user.id,
            action_type=payload.get("action_type") or "",
            priority=priority,
        )
    except IntelligenceActionValidationError as error:
        return validation_error(str(error))
    except IntelligenceActionExecutionError as error:
        return jsonify({"error": "action_proposal_failed", "message": str(error)}), 503
    return jsonify({"proposal": proposal_to_dict(proposal)}), 201


@intelligence_api_bp.get("/action-proposals/<int:proposal_id>")
@api_auth_required
def action_proposal_details_route(proposal_id: int):
    try:
        proposal = require_owned_proposal(proposal_id=proposal_id, owner_id=current_user.id)
    except IntelligenceActionNotFoundError:
        return not_found("Action proposal not found.")
    return jsonify({"proposal": proposal_to_dict(proposal)})


@intelligence_api_bp.post("/action-proposals/<int:proposal_id>/confirm")
@api_auth_required
def confirm_action_proposal_route(proposal_id: int):
    """Execute a reviewed action only after this explicit authenticated confirm."""

    try:
        proposal = confirm_owned_action_proposal(proposal_id=proposal_id, owner_id=current_user.id)
    except IntelligenceActionNotFoundError:
        return not_found("Action proposal not found.")
    except IntelligenceActionValidationError as error:
        return validation_error(str(error))
    except IntelligenceActionExecutionError as error:
        return jsonify({"error": "action_execution_failed", "message": str(error)}), 503
    return jsonify({"proposal": proposal_to_dict(proposal), "changed": True})


@intelligence_api_bp.post("/action-proposals/<int:proposal_id>/dismiss")
@api_auth_required
def dismiss_action_proposal_route(proposal_id: int):
    try:
        proposal = dismiss_owned_action_proposal(proposal_id=proposal_id, owner_id=current_user.id)
    except IntelligenceActionNotFoundError:
        return not_found("Action proposal not found.")
    except IntelligenceActionValidationError as error:
        return validation_error(str(error))
    except IntelligenceActionExecutionError as error:
        return jsonify({"error": "action_dismiss_failed", "message": str(error)}), 503
    return jsonify({"proposal": proposal_to_dict(proposal), "changed": False})


@intelligence_api_bp.get("/activity")
@api_auth_required
def recent_activity_route():
    """Expose I10 deterministic recent activity without AI generation."""

    raw_project_id = request.args.get("project_id")
    project_id = None
    if raw_project_id not in (None, ""):
        try:
            project_id = int(raw_project_id)
        except (TypeError, ValueError):
            return validation_error("Invalid project selected.")
    try:
        activity = build_owned_recent_activity(
            owner_id=current_user.id,
            query=request.args.get("q", ""),
            project_id=project_id,
        )
    except LookupError:
        return not_found("Project not found.")
    return jsonify({"activity": activity.to_dict()})

@intelligence_api_bp.post("/events/scan")
@api_auth_required
def intelligence_event_scan_route():
    """Run I14 event detection over the authenticated owner's trusted state."""

    result = scan_owned_intelligence_events(owner_id=current_user.id)
    return jsonify({"event_scan": result.to_dict()})


@intelligence_api_bp.get("/events")
@api_auth_required
def intelligence_events_route():
    """List normalized I14 events without exposing other users or raw content."""

    lifecycle = request.args.get("lifecycle") or None
    try:
        limit = int(request.args.get("limit", "50"))
    except (TypeError, ValueError):
        return validation_error("Invalid event limit.")
    events = list_owned_intelligence_events(
        owner_id=current_user.id, lifecycle=lifecycle, limit=limit
    )
    return jsonify({"events": [event_to_dict(event) for event in events]})


@intelligence_api_bp.post("/proactive/refresh")
@api_auth_required
def proactive_refresh_route():
    """Refresh I14 and return I15 in-app notices; no workspace action is executed."""

    result = refresh_owned_proactive_notifications(owner_id=current_user.id)
    return jsonify({"proactive": result.to_dict()})


@intelligence_api_bp.get("/proactive")
@api_auth_required
def proactive_notifications_route():
    try:
        limit = int(request.args.get("limit", "20"))
    except (TypeError, ValueError):
        return validation_error("Invalid notification limit.")
    result = list_owned_proactive_notifications(owner_id=current_user.id, limit=limit)
    return jsonify({"proactive": result.to_dict()})


@intelligence_api_bp.post("/proactive/<int:notification_id>/read")
@api_auth_required
def proactive_notification_read_route(notification_id: int):
    try:
        item = mark_owned_proactive_notification_read(
            owner_id=current_user.id, notification_id=notification_id
        )
    except ProactiveNotificationNotFoundError:
        return not_found("Notification not found.")
    return jsonify({"notification": notification_to_dict(item)})


@intelligence_api_bp.post("/proactive/<int:notification_id>/dismiss")
@api_auth_required
def proactive_notification_dismiss_route(notification_id: int):
    try:
        item = dismiss_owned_proactive_notification(
            owner_id=current_user.id, notification_id=notification_id
        )
    except ProactiveNotificationNotFoundError:
        return not_found("Notification not found.")
    return jsonify({"notification": notification_to_dict(item)})


@intelligence_api_bp.post("/proactive/read-all")
@api_auth_required
def proactive_read_all_route():
    changed = mark_all_owned_proactive_notifications_read(owner_id=current_user.id)
    return jsonify({"changed": changed})


@intelligence_api_bp.get("/connections/<string:resource_type>/<int:resource_id>")
@api_auth_required
def context_connections_route(resource_type: str, resource_id: int):
    """Return I13 verified connections for one owned LifeOS resource."""

    try:
        result = build_owned_context_connections(
            owner_id=current_user.id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
    except ContextConnectionValidationError as error:
        return validation_error(str(error))
    except ContextConnectionNotFoundError:
        return not_found("Resource not found.")
    return jsonify({"connections": result.to_dict()})

@intelligence_api_bp.post("/memory/refresh")
@api_auth_required
def memory_refresh_route():
    """Refresh I16's safe derived memory without changing workspace resources."""

    result = refresh_owned_structured_memory(owner_id=current_user.id)
    return jsonify({"memory": result.to_dict(), "workspace_mutation": False})


@intelligence_api_bp.get("/memory")
@api_auth_required
def memory_list_route():
    memory_type = request.args.get("type") or None
    try:
        result = list_owned_memories(owner_id=current_user.id, memory_type=memory_type)
    except StructuredMemoryValidationError as error:
        return validation_error(str(error))
    return jsonify({"memory": result.to_dict()})


@intelligence_api_bp.post("/memory")
@api_auth_required
def memory_save_route():
    """Save only an explicit preference or current-focus memory."""

    payload = json_body()
    try:
        item = save_owned_user_memory(
            owner_id=current_user.id,
            memory_type=payload.get("type") or "",
            key=payload.get("key"),
            label=payload.get("label") or "",
            value=payload.get("value") or "",
            project_id=payload.get("project_id"),
        )
    except (StructuredMemoryValidationError, TypeError, ValueError) as error:
        return validation_error(str(error))
    return jsonify({"memory": memory_to_dict(item)}), 201


@intelligence_api_bp.delete("/memory/<int:memory_id>")
@api_auth_required
def memory_delete_route(memory_id: int):
    try:
        delete_owned_memory(owner_id=current_user.id, memory_id=memory_id)
    except StructuredMemoryNotFoundError:
        return not_found("Memory not found.")
    return jsonify({"deleted": True, "memory_id": memory_id})


@intelligence_api_bp.post("/memory/clear")
@api_auth_required
def memory_clear_route():
    deleted = clear_owned_memories(owner_id=current_user.id)
    return jsonify({"deleted": deleted})


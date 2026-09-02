"""I19 constrained LifeOS Agent Runtime API."""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user

from lifeos.api.v1.common import api_auth_required, json_body, not_found, validation_error
from services.agent_planner_service import AgentPlannerError, plan_owned_agent_goal
from services.agent_runtime_service import (
    AgentProposalError,
    AgentRunNotFoundError,
    AgentRuntimeError,
    agent_registry_payload,
    agent_run_to_dict,
    list_owned_agent_runs,
    prepare_agent_action_proposal,
    require_owned_agent_run,
    run_owned_agent_goal,
)
from services.ask_context_picker_service import AskContextNotFoundError, AskContextValidationError
from services.intelligence_action_service import proposal_to_dict

agent_api_bp = Blueprint("api_v1_agent", __name__, url_prefix="/api/v1/agent")


@agent_api_bp.get("/registry")
@api_auth_required
def agent_registry_route():
    return jsonify(agent_registry_payload())


@agent_api_bp.post("/plan")
@api_auth_required
def agent_plan_route():
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


@agent_api_bp.post("/runs")
@api_auth_required
def agent_run_route():
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
        return jsonify({"error": "agent_runtime_failed", "message": str(error)}), 503
    return jsonify({"run": agent_run_to_dict(run)}), 201


@agent_api_bp.get("/runs")
@api_auth_required
def agent_runs_route():
    raw_limit = request.args.get("limit", "12")
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return validation_error("Invalid agent history limit.")
    return jsonify({"runs": list_owned_agent_runs(owner_id=current_user.id, limit=limit)})


@agent_api_bp.get("/runs/<int:run_id>")
@api_auth_required
def agent_run_details_route(run_id: int):
    try:
        run = require_owned_agent_run(owner_id=current_user.id, run_id=run_id)
    except AgentRunNotFoundError:
        return not_found("Agent run not found.")
    return jsonify({"run": agent_run_to_dict(run)})


@agent_api_bp.post("/runs/<int:run_id>/proposals")
@api_auth_required
def agent_prepare_proposal_route(run_id: int):
    payload = json_body()
    try:
        proposal = prepare_agent_action_proposal(
            owner_id=current_user.id,
            run_id=run_id,
            suggestion_id=str(payload.get("suggestion_id") or ""),
            action_type=str(payload.get("action_type") or ""),
        )
    except AgentRunNotFoundError:
        return not_found("Agent run not found.")
    except AgentProposalError as error:
        return validation_error(str(error))
    return jsonify({"proposal": proposal_to_dict(proposal)}), 201

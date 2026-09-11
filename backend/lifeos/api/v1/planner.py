"""Smart Planner V1 API.

Plan generation and rebalance previews are read-only. AI-generated schedule writes
still go through I9 confirmation. Manual commitment/block edits are explicit
user UI actions handled deterministically by the planner service.
"""

from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, jsonify, request
from flask_login import current_user

from lifeos.api.v1.common import api_auth_required, json_body, validation_error
from services.intelligence_action_service import proposal_to_dict
from services.smart_planner_service import (
    SmartPlannerPersistenceError,
    SmartPlannerValidationError,
    build_natural_language_plan_preview,
    build_rebalance_preview,
    build_smart_plan_preview,
    commitment_to_dict,
    create_owned_commitment,
    delete_owned_commitment,
    fixed_commitments,
    planner_state,
    prepare_natural_language_plan_proposal,
    prepare_rebalance_proposal,
    prepare_smart_plan_proposal,
    smart_plan_to_dict,
    update_owned_commitment,
    update_owned_plan_block,
)


planner_api_bp = Blueprint("api_v1_planner", __name__, url_prefix="/api/v1/planner")


def _optional_date(value: str | None, message: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise SmartPlannerValidationError(message) from error


@planner_api_bp.get("")
@api_auth_required
def planner_state_route():
    try:
        target_date = _optional_date(request.args.get("date"), "Choose a valid planner date.")
    except SmartPlannerValidationError as error:
        return validation_error(str(error))
    return jsonify({"planner": planner_state(owner_id=current_user.id, target_date=target_date)})


@planner_api_bp.post("/preview")
@api_auth_required
def planner_preview_route():
    try:
        preview = build_smart_plan_preview(owner_id=current_user.id, payload=json_body())
    except SmartPlannerValidationError as error:
        return validation_error(str(error))
    return jsonify({"preview": preview})


@planner_api_bp.post("/natural-preview")
@api_auth_required
def planner_natural_preview_route():
    try:
        preview = build_natural_language_plan_preview(owner_id=current_user.id, payload=json_body())
    except SmartPlannerValidationError as error:
        return validation_error(str(error))
    return jsonify({"preview": preview, "interpretation": preview.get("interpretation")})


@planner_api_bp.post("/natural-proposals")
@api_auth_required
def planner_natural_proposal_route():
    try:
        proposal = prepare_natural_language_plan_proposal(owner_id=current_user.id, payload=json_body())
    except SmartPlannerValidationError as error:
        return validation_error(str(error))
    except SmartPlannerPersistenceError as error:
        return jsonify({"error": "planner_proposal_failed", "message": str(error)}), 503
    return jsonify({"proposal": proposal_to_dict(proposal)}), 201


@planner_api_bp.post("/proposals")
@api_auth_required
def planner_proposal_route():
    try:
        proposal = prepare_smart_plan_proposal(owner_id=current_user.id, payload=json_body())
    except SmartPlannerValidationError as error:
        return validation_error(str(error))
    except SmartPlannerPersistenceError as error:
        return jsonify({"error": "planner_proposal_failed", "message": str(error)}), 503
    return jsonify({"proposal": proposal_to_dict(proposal)}), 201


@planner_api_bp.get("/commitments")
@api_auth_required
def planner_commitments_route():
    try:
        start = _optional_date(request.args.get("start_date"), "Choose a valid commitment start date.") or date.today()
        end = _optional_date(request.args.get("end_date"), "Choose a valid commitment end date.") or (start + timedelta(days=13))
        if end < start or (end - start).days > 31:
            raise SmartPlannerValidationError("Commitment range must be between 1 and 32 days.")
        items = fixed_commitments(owner_id=current_user.id, start_date=start, end_date=end)
    except SmartPlannerValidationError as error:
        return validation_error(str(error))
    return jsonify({"commitments": items})


@planner_api_bp.post("/commitments")
@api_auth_required
def planner_commitment_create_route():
    try:
        row = create_owned_commitment(owner_id=current_user.id, payload=json_body())
    except SmartPlannerValidationError as error:
        return validation_error(str(error))
    except SmartPlannerPersistenceError as error:
        return jsonify({"error": "planner_commitment_failed", "message": str(error)}), 503
    return jsonify({"commitment": commitment_to_dict(row)}), 201


@planner_api_bp.patch("/commitments/<int:commitment_id>")
@api_auth_required
def planner_commitment_update_route(commitment_id: int):
    try:
        row = update_owned_commitment(owner_id=current_user.id, commitment_id=commitment_id, payload=json_body())
    except SmartPlannerValidationError as error:
        return validation_error(str(error))
    except SmartPlannerPersistenceError as error:
        return jsonify({"error": "planner_commitment_failed", "message": str(error)}), 503
    return jsonify({"commitment": commitment_to_dict(row)})


@planner_api_bp.delete("/commitments/<int:commitment_id>")
@api_auth_required
def planner_commitment_delete_route(commitment_id: int):
    try:
        delete_owned_commitment(owner_id=current_user.id, commitment_id=commitment_id)
    except SmartPlannerValidationError as error:
        return validation_error(str(error))
    except SmartPlannerPersistenceError as error:
        return jsonify({"error": "planner_commitment_failed", "message": str(error)}), 503
    return jsonify({"deleted": True})


@planner_api_bp.patch("/plans/<int:plan_id>/blocks/<int:block_id>")
@api_auth_required
def planner_block_update_route(plan_id: int, block_id: int):
    try:
        plan = update_owned_plan_block(owner_id=current_user.id, plan_id=plan_id, block_id=block_id, payload=json_body())
    except SmartPlannerValidationError as error:
        return validation_error(str(error))
    except SmartPlannerPersistenceError as error:
        return jsonify({"error": "planner_block_update_failed", "message": str(error)}), 503
    return jsonify({"plan": smart_plan_to_dict(plan)})


@planner_api_bp.post("/plans/<int:plan_id>/rebalance-preview")
@api_auth_required
def planner_rebalance_preview_route(plan_id: int):
    raw = json_body()
    try:
        from_date = _optional_date(str(raw.get("from_date") or "") or None, "Choose a valid rebalance date.")
        preview = build_rebalance_preview(owner_id=current_user.id, plan_id=plan_id, from_date=from_date)
    except SmartPlannerValidationError as error:
        return validation_error(str(error))
    return jsonify({"preview": preview})


@planner_api_bp.post("/plans/<int:plan_id>/rebalance-proposals")
@api_auth_required
def planner_rebalance_proposal_route(plan_id: int):
    raw = json_body()
    try:
        from_date = _optional_date(str(raw.get("from_date") or "") or None, "Choose a valid rebalance date.")
        proposal = prepare_rebalance_proposal(owner_id=current_user.id, plan_id=plan_id, from_date=from_date)
    except SmartPlannerValidationError as error:
        return validation_error(str(error))
    except SmartPlannerPersistenceError as error:
        return jsonify({"error": "planner_rebalance_failed", "message": str(error)}), 503
    return jsonify({"proposal": proposal_to_dict(proposal)}), 201

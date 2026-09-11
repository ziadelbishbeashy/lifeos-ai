"""I17 automation API plus I18 visual graph validation/compilation endpoints."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user

from lifeos.api.v1.common import api_auth_required, json_body, not_found, validation_error
from services.automation_flow_execution_service import AutomationFlowExecutionError
from services.automation_engine_service import (
    collect_owned_automation_candidates,
    execute_owned_automation,
    execute_owned_automation_cycle,
)
from services.automation_service import (
    AutomationNotFoundError,
    AutomationValidationError,
    automation_registry,
    automation_run_to_dict,
    clear_owned_automation_error,
    automation_to_dict,
    compile_owned_visual_flow_draft,
    create_owned_automation,
    delete_owned_automation,
    list_owned_automation_runs,
    list_owned_automations,
    preview_owned_automation,
    update_owned_automation,
)


automations_api_bp = Blueprint(
    "api_v1_automations",
    __name__,
    url_prefix="/api/v1/automations",
)


@automations_api_bp.get("/registry")
@api_auth_required
def automation_registry_route():
    return jsonify({
        "registry": automation_registry(),
        "runtime": {
            "worker_enabled": bool(current_app.config.get("ENABLE_LIFEOS_AUTOMATIONS", False)),
            "poll_seconds": int(current_app.config.get("LIFEOS_AUTOMATION_POLL_SECONDS", 60)),
            "execution_available": True,
            "workspace_mutation": False,
        },
    })


@automations_api_bp.post("/compile")
@api_auth_required
def automation_compile_draft_route():
    """Validate + compile a visual draft without persistence or execution."""

    payload = json_body()
    try:
        result = compile_owned_visual_flow_draft(
            owner_id=current_user.id,
            trigger_type=payload.get("trigger_type"),
            trigger_config=payload.get("trigger_config"),
            action_type=payload.get("action_type"),
            action_config=payload.get("action_config"),
            visual_graph=payload.get("visual_graph"),
        )
    except AutomationValidationError as error:
        return validation_error(str(error))
    return jsonify(result)


@automations_api_bp.post("/candidates/scan")
@api_auth_required
def automation_candidates_route():
    """Evaluate due/event trigger candidates without executing them."""

    result = collect_owned_automation_candidates(owner_id=current_user.id)
    return jsonify({"candidate_scan": result.to_dict()})


@automations_api_bp.get("")
@api_auth_required
def automations_list_route():
    items = list_owned_automations(owner_id=current_user.id)
    return jsonify({
        "automations": [automation_to_dict(item) for item in items],
        "count": len(items),
        "preparation_mode": False,
        "execution_available": True,
        "worker_enabled": bool(current_app.config.get("ENABLE_LIFEOS_AUTOMATIONS", False)),
    })


@automations_api_bp.post("")
@api_auth_required
def automation_create_route():
    payload = json_body()
    try:
        item = create_owned_automation(
            owner_id=current_user.id,
            name=payload.get("name"),
            description=payload.get("description"),
            enabled=bool(payload.get("enabled", False)),
            trigger_type=payload.get("trigger_type"),
            trigger_config=payload.get("trigger_config"),
            action_type=payload.get("action_type"),
            action_config=payload.get("action_config"),
            timezone_name=payload.get("timezone") or "UTC",
            visual_graph=payload.get("visual_graph"),
        )
    except AutomationValidationError as error:
        return validation_error(str(error))
    return jsonify({"automation": automation_to_dict(item)}), 201


@automations_api_bp.patch("/<int:automation_id>")
@api_auth_required
def automation_update_route(automation_id: int):
    payload = json_body()
    try:
        item = update_owned_automation(
            owner_id=current_user.id,
            automation_id=automation_id,
            payload=payload,
        )
    except AutomationNotFoundError:
        return not_found("Automation not found.")
    except AutomationValidationError as error:
        return validation_error(str(error))
    return jsonify({"automation": automation_to_dict(item)})


@automations_api_bp.delete("/<int:automation_id>")
@api_auth_required
def automation_delete_route(automation_id: int):
    try:
        delete_owned_automation(owner_id=current_user.id, automation_id=automation_id)
    except AutomationNotFoundError:
        return not_found("Automation not found.")
    return jsonify({"deleted": True, "automation_id": automation_id})


@automations_api_bp.post("/<int:automation_id>/preview")
@api_auth_required
def automation_preview_route(automation_id: int):
    payload = json_body()
    raw_event_id = payload.get("event_id")
    event_id = None
    if raw_event_id not in (None, ""):
        try:
            event_id = int(raw_event_id)
        except (TypeError, ValueError):
            return validation_error("Invalid event selected.")
    try:
        result = preview_owned_automation(
            owner_id=current_user.id,
            automation_id=automation_id,
            event_id=event_id,
        )
    except AutomationNotFoundError:
        return not_found("Automation not found.")
    except (AutomationValidationError, AutomationFlowExecutionError) as error:
        return validation_error(str(error))
    return jsonify({"preview": result.to_dict()})


@automations_api_bp.post("/<int:automation_id>/run")
@api_auth_required
def automation_run_now_route(automation_id: int):
    """Explicitly run one automation now; still read-only with respect to workspace state."""

    try:
        result = execute_owned_automation(
            owner_id=current_user.id,
            automation_id=automation_id,
            trigger_source="manual",
        )
    except AutomationNotFoundError:
        return not_found("Automation not found.")
    except (AutomationValidationError, AutomationFlowExecutionError) as error:
        return validation_error(str(error))
    return jsonify({"execution": result.to_dict()})


@automations_api_bp.post("/cycle/run")
@api_auth_required
def automation_cycle_run_route():
    """Execute the signed-in user's automations that are due/matched right now."""

    result = execute_owned_automation_cycle(owner_id=current_user.id)
    return jsonify({"cycle": result.to_dict()})




@automations_api_bp.post("/<int:automation_id>/clear-error")
@api_auth_required
def automation_clear_error_route(automation_id: int):
    """Clear visible error state while preserving immutable run history."""

    try:
        item = clear_owned_automation_error(owner_id=current_user.id, automation_id=automation_id)
    except AutomationNotFoundError:
        return not_found("Automation not found.")
    except AutomationValidationError as error:
        return validation_error(str(error))
    return jsonify({"automation": automation_to_dict(item), "history_preserved": True})


@automations_api_bp.get("/<int:automation_id>/runs")
@api_auth_required
def automation_runs_route(automation_id: int):
    try:
        limit = int(request.args.get("limit", "20"))
    except (TypeError, ValueError):
        return validation_error("Invalid run-history limit.")
    try:
        items = list_owned_automation_runs(
            owner_id=current_user.id,
            automation_id=automation_id,
            limit=limit,
        )
    except AutomationNotFoundError:
        return not_found("Automation not found.")
    return jsonify({"runs": [automation_run_to_dict(item) for item in items]})

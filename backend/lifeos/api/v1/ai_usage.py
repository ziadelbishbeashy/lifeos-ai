"""Authenticated AI usage/cost observability API."""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user

from lifeos.api.v1.common import api_auth_required, validation_error
from services.ai_usage_service import list_owned_usage_events, summarize_owned_usage


ai_usage_api_bp = Blueprint("api_v1_ai_usage", __name__, url_prefix="/api/v1/ai-usage")


@ai_usage_api_bp.get("/summary")
@api_auth_required
def ai_usage_summary_route():
    raw_days = request.args.get("days", "30")
    try:
        days = int(raw_days)
    except (TypeError, ValueError):
        return validation_error("Invalid AI usage period.")
    return jsonify(summarize_owned_usage(user_id=current_user.id, days=days))


@ai_usage_api_bp.get("/recent")
@api_auth_required
def ai_usage_recent_route():
    raw_limit = request.args.get("limit", "50")
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return validation_error("Invalid AI usage history limit.")
    return jsonify({"items": list_owned_usage_events(user_id=current_user.id, limit=limit)})

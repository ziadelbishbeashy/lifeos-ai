from __future__ import annotations

from datetime import datetime

from flask import Blueprint, Response, jsonify, request
from flask_login import current_user

from lifeos.api.v1.common import api_auth_required
from lifeos.api.v1.serializers import json_safe
from services.analytics_service import focus_export_rows, get_analytics_dashboard, task_export_rows
from services.export_service import build_csv

analytics_api_bp = Blueprint("api_v1_analytics", __name__, url_prefix="/api/v1/analytics")


@analytics_api_bp.get("")
@api_auth_required
def analytics_dashboard_route():
    analytics = get_analytics_dashboard(
        user_id=current_user.id,
        period=request.args.get("period", "month"),
        start_value=request.args.get("start"),
        end_value=request.args.get("end"),
    )
    return jsonify(json_safe(analytics))


def _csv_response(rows, fieldnames, filename):
    response = Response(
        build_csv(rows, fieldnames),
        mimetype="text/csv; charset=utf-8",
    )
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@analytics_api_bp.get("/exports/tasks.csv")
@api_auth_required
def export_tasks_csv_api():
    fieldnames = [
        "task_id", "title", "scope", "status", "importance", "difficulty",
        "module", "deadline", "created_at", "completed_at", "is_recurring",
        "recurrence_type",
    ]
    filename = f"lifeos_tasks_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return _csv_response(task_export_rows(current_user.id), fieldnames, filename)


@analytics_api_bp.get("/exports/focus.csv")
@api_auth_required
def export_focus_csv_api():
    fieldnames = [
        "session_id", "title", "task", "project", "goal", "planned_minutes",
        "actual_minutes", "status", "distractions", "focus_rating",
        "goal_result", "completed_at",
    ]
    filename = f"lifeos_focus_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return _csv_response(focus_export_rows(current_user.id), fieldnames, filename)

import csv
import io
from datetime import datetime

from flask import Blueprint, Response, render_template, request
from flask_login import current_user, login_required

from services.analytics_service import (
    focus_export_rows,
    get_analytics_dashboard,
    task_export_rows,
)


analytics_bp = Blueprint("analytics_bp", __name__, url_prefix="/analytics")


@analytics_bp.before_request
@login_required
def protect_analytics_routes():
    return None


def _current_filter_values():
    return {
        "period": request.args.get("period", "month"),
        "start": request.args.get("start"),
        "end": request.args.get("end"),
    }


@analytics_bp.route("")
@analytics_bp.route("/")
def analytics_dashboard():
    filters = _current_filter_values()
    analytics = get_analytics_dashboard(
        user_id=current_user.id,
        period=filters["period"],
        start_value=filters["start"],
        end_value=filters["end"],
    )

    return render_template(
        "analytics.html",
        analytics=analytics,
        selected_period=analytics["range"].key,
        custom_start=analytics["range"].start_date.isoformat(),
        custom_end=analytics["range"].end_date.isoformat(),
    )


def _csv_response(rows, fieldnames, filename):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@analytics_bp.route("/export/tasks.csv")
def export_tasks_csv():
    rows = task_export_rows(current_user.id)
    fieldnames = [
        "task_id",
        "title",
        "scope",
        "status",
        "importance",
        "difficulty",
        "module",
        "deadline",
        "created_at",
        "completed_at",
        "is_recurring",
        "recurrence_type",
    ]
    filename = f"lifeos_tasks_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return _csv_response(rows, fieldnames, filename)


@analytics_bp.route("/export/focus.csv")
def export_focus_csv():
    rows = focus_export_rows(current_user.id)
    fieldnames = [
        "session_id",
        "title",
        "task",
        "project",
        "goal",
        "planned_minutes",
        "actual_minutes",
        "status",
        "distractions",
        "focus_rating",
        "goal_result",
        "completed_at",
    ]
    filename = f"lifeos_focus_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return _csv_response(rows, fieldnames, filename)

from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from flask_login import current_user

from lifeos.api.v1.common import api_auth_required, json_body, persistence_error
from lifeos.api.v1.serializers import serialize_notification_log, serialize_notification_preferences
from services.email_service import email_is_configured
from services.notification_preferences_service import (
    NotificationPreferencePersistenceError,
    recent_notification_logs,
    update_notification_preferences,
)
from services.notification_service import (
    get_or_create_notification_preferences,
    run_email_notification_check,
    send_daily_summary_email,
    send_monthly_analytics_email,
    send_test_email,
    send_weekly_summary_email,
)

notifications_api_bp = Blueprint("api_v1_notifications", __name__, url_prefix="/api/v1/notifications")


def _form_from_json(payload: dict) -> dict:
    # Existing preference validation consumes form-style truthy values and text.
    return {
        key: ("on" if value is True else "" if value is False else value)
        for key, value in payload.items()
    }


@notifications_api_bp.get("/settings")
@api_auth_required
def settings_route():
    preferences = get_or_create_notification_preferences(current_user)
    return jsonify({
        "preferences": serialize_notification_preferences(preferences),
        "recent_logs": [serialize_notification_log(x) for x in recent_notification_logs(current_user.id, 8)],
        "email_configured": bool(email_is_configured()),
    })


@notifications_api_bp.patch("/settings")
@api_auth_required
def update_settings_route():
    try:
        preferences = update_notification_preferences(current_user, _form_from_json(json_body()))
    except NotificationPreferencePersistenceError:
        current_app.logger.exception("API notification settings save failed")
        return persistence_error("Notification settings could not be saved.")
    return jsonify({"preferences": serialize_notification_preferences(preferences)})


@notifications_api_bp.get("/history")
@api_auth_required
def history_route():
    return jsonify({"items": [serialize_notification_log(x) for x in recent_notification_logs(current_user.id, 100)]})


def _require_email():
    if email_is_configured():
        return None
    return jsonify({"error": "email_not_configured", "message": "Email is not configured yet. Add MAIL settings to the backend environment."}), 409


@notifications_api_bp.post("/email/test")
@api_auth_required
def test_email_route():
    blocked = _require_email()
    if blocked:
        return blocked
    try:
        send_test_email(current_user)
    except Exception:
        current_app.logger.exception("API test email failed")
        return persistence_error("Test email could not be sent. Check your email settings.")
    return jsonify({"message": "Test email sent successfully."})


@notifications_api_bp.post("/email/check")
@api_auth_required
def email_check_route():
    blocked = _require_email()
    if blocked:
        return blocked
    try:
        result = run_email_notification_check(user_id=current_user.id, include_automatic_summaries=True)
    except Exception:
        current_app.logger.exception("API email check failed")
        return persistence_error("Email notification check failed.")
    return jsonify({"message": "Email notification check finished.", "result": result})


@notifications_api_bp.post("/email/daily-summary")
@api_auth_required
def daily_summary_route():
    blocked = _require_email()
    if blocked:
        return blocked
    try:
        sent = send_daily_summary_email(current_user, force=True)
    except Exception:
        current_app.logger.exception("API daily summary failed")
        return persistence_error("Daily checkup email could not be sent.")
    return jsonify({"sent": bool(sent), "message": "Daily checkup email sent successfully." if sent else "Daily checkup was already sent today."})


@notifications_api_bp.post("/email/weekly-summary")
@api_auth_required
def weekly_summary_route():
    blocked = _require_email()
    if blocked:
        return blocked
    try:
        sent = send_weekly_summary_email(current_user, force=True)
    except Exception:
        current_app.logger.exception("API weekly summary failed")
        return persistence_error("Weekly summary email could not be sent.")
    return jsonify({"sent": bool(sent), "message": "Weekly summary email sent successfully." if sent else "Weekly summary was already sent this week."})


@notifications_api_bp.post("/email/monthly-analytics")
@api_auth_required
def monthly_summary_route():
    blocked = _require_email()
    if blocked:
        return blocked
    try:
        sent = send_monthly_analytics_email(current_user, force=True)
    except Exception:
        current_app.logger.exception("API monthly analytics failed")
        return persistence_error("Monthly analytics email could not be sent.")
    return jsonify({"sent": bool(sent), "message": "Monthly analytics email sent successfully." if sent else "Monthly analytics email was already sent this month."})

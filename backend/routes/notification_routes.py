"""HTTP routes for LifeOS email notification preferences and actions."""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

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


notification_bp = Blueprint("notification_bp", __name__)


@notification_bp.before_request
@login_required
def protect_notification_routes():
    return None


def _email_required_redirect():
    if email_is_configured():
        return None
    flash(
        "Email is not configured yet. Add MAIL settings to your .env file.",
        "error",
    )
    return redirect(url_for("notification_bp.notification_settings"))


def _return_to_origin():
    return redirect(request.referrer or url_for("dashboard"))


@notification_bp.route("/notifications/settings", methods=["GET", "POST"])
def notification_settings():
    preferences = get_or_create_notification_preferences(current_user)

    if request.method == "POST":
        try:
            preferences = update_notification_preferences(
                current_user,
                request.form,
            )
            flash("Notification preferences saved successfully.", "success")
        except NotificationPreferencePersistenceError:
            current_app.logger.exception(
                "LifeOS could not save notification preferences for user %s.",
                current_user.id,
            )
            flash("Notification settings could not be saved.", "error")
        return redirect(url_for("notification_bp.notification_settings"))

    return render_template(
        "notification_settings.html",
        preferences=preferences,
        recent_logs=recent_notification_logs(current_user.id, 8),
        email_configured=email_is_configured(),
    )


@notification_bp.route("/notifications/history")
def notification_history():
    return render_template(
        "notification_history.html",
        logs=recent_notification_logs(current_user.id, 100),
    )


@notification_bp.route("/notifications/email/test", methods=["POST"])
def send_test_notification_email():
    blocked = _email_required_redirect()
    if blocked:
        return blocked
    try:
        send_test_email(current_user)
        flash("Test email sent successfully.", "success")
    except Exception:
        current_app.logger.exception(
            "LifeOS could not send a test email for user %s.",
            current_user.id,
        )
        flash("Test email could not be sent. Check your email settings.", "error")
    return _return_to_origin()


@notification_bp.route("/notifications/email/check", methods=["POST"])
def run_my_email_notification_check():
    blocked = _email_required_redirect()
    if blocked:
        return blocked
    try:
        result = run_email_notification_check(
            user_id=current_user.id,
            include_automatic_summaries=True,
        )
        flash(
            "Email check finished: "
            f"{result['custom_reminders_sent']} custom reminder(s), "
            f"{result['deadline_reminders_sent']} deadline reminder(s), "
            f"{result['daily_summaries_sent']} daily checkup(s), "
            f"{result['weekly_summaries_sent']} weekly summary email(s), "
            f"{result['monthly_reports_sent']} monthly report(s).",
            "success",
        )
    except Exception:
        current_app.logger.exception(
            "LifeOS email notification check failed for user %s.",
            current_user.id,
        )
        flash("Email notification check failed.", "error")
    return _return_to_origin()


@notification_bp.route("/notifications/email/daily-summary", methods=["POST"])
def send_my_daily_summary():
    blocked = _email_required_redirect()
    if blocked:
        return blocked
    try:
        was_sent = send_daily_summary_email(current_user, force=True)
        flash(
            "Daily checkup email sent successfully."
            if was_sent
            else "Daily checkup was already sent today.",
            "success" if was_sent else "info",
        )
    except Exception:
        current_app.logger.exception(
            "LifeOS daily summary failed for user %s.",
            current_user.id,
        )
        flash("Daily checkup email could not be sent.", "error")
    return _return_to_origin()


@notification_bp.route("/notifications/email/weekly-summary", methods=["POST"])
def send_my_weekly_summary():
    blocked = _email_required_redirect()
    if blocked:
        return blocked
    try:
        was_sent = send_weekly_summary_email(current_user, force=True)
        flash(
            "Weekly summary email sent successfully."
            if was_sent
            else "Weekly summary was already sent this week.",
            "success" if was_sent else "info",
        )
    except Exception:
        current_app.logger.exception(
            "LifeOS weekly summary failed for user %s.",
            current_user.id,
        )
        flash("Weekly summary email could not be sent.", "error")
    return _return_to_origin()


@notification_bp.route("/notifications/email/monthly-analytics", methods=["POST"])
def send_my_monthly_analytics():
    blocked = _email_required_redirect()
    if blocked:
        return blocked
    try:
        was_sent = send_monthly_analytics_email(current_user, force=True)
        flash(
            "Monthly analytics email sent successfully."
            if was_sent
            else "Monthly analytics email was already sent this month.",
            "success" if was_sent else "info",
        )
    except Exception:
        current_app.logger.exception(
            "LifeOS monthly analytics failed for user %s.",
            current_user.id,
        )
        flash("Monthly analytics email could not be sent.", "error")
    return _return_to_origin()

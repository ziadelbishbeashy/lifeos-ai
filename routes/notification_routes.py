from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from database import db
from models import EmailNotificationLog
from services.email_service import email_is_configured
from services.notification_service import (
    get_or_create_notification_preferences,
    run_email_notification_check,
    send_daily_summary_email,
    send_monthly_analytics_email,
    send_test_email,
    send_weekly_summary_email,
)


notification_bp = Blueprint("notification_bp", __name__)


TRUE_FORM_VALUES = {"on", "true", "1", "yes"}


def _checkbox_enabled(form, name):
    return (form.get(name) or "").lower() in TRUE_FORM_VALUES


def _int_value(form, name, default, min_value=None, max_value=None):
    try:
        value = int(form.get(name, default))
    except (TypeError, ValueError):
        value = default

    if min_value is not None:
        value = max(min_value, value)

    if max_value is not None:
        value = min(max_value, value)

    return value


def _time_value(form, name, default):
    raw_value = form.get(name)

    if not raw_value:
        return default

    try:
        return datetime.strptime(raw_value, "%H:%M").time()
    except ValueError:
        return default


def _optional_time_value(form, name):
    raw_value = form.get(name)

    if not raw_value:
        return None

    try:
        return datetime.strptime(raw_value, "%H:%M").time()
    except ValueError:
        return None


@notification_bp.route("/notifications/settings", methods=["GET", "POST"])
@login_required
def notification_settings():
    preferences = get_or_create_notification_preferences(current_user)

    if request.method == "POST":
        preferences.email_enabled = _checkbox_enabled(request.form, "email_enabled")
        preferences.task_reminders_enabled = _checkbox_enabled(
            request.form,
            "task_reminders_enabled",
        )
        preferences.custom_task_reminders_enabled = _checkbox_enabled(
            request.form,
            "custom_task_reminders_enabled",
        )
        preferences.overdue_alerts_enabled = _checkbox_enabled(
            request.form,
            "overdue_alerts_enabled",
        )
        preferences.project_deadline_alerts_enabled = _checkbox_enabled(
            request.form,
            "project_deadline_alerts_enabled",
        )
        preferences.project_risk_alerts_enabled = _checkbox_enabled(
            request.form,
            "project_risk_alerts_enabled",
        )
        preferences.daily_checkup_enabled = _checkbox_enabled(
            request.form,
            "daily_checkup_enabled",
        )
        preferences.weekly_summary_enabled = _checkbox_enabled(
            request.form,
            "weekly_summary_enabled",
        )
        preferences.monthly_analytics_enabled = _checkbox_enabled(
            request.form,
            "monthly_analytics_enabled",
        )

        preferences.task_reminder_days_before = _int_value(
            request.form,
            "task_reminder_days_before",
            1,
            0,
            14,
        )
        preferences.project_reminder_days_before = _int_value(
            request.form,
            "project_reminder_days_before",
            3,
            0,
            30,
        )
        preferences.weekly_summary_day = _int_value(
            request.form,
            "weekly_summary_day",
            6,
            0,
            6,
        )
        preferences.monthly_report_day = _int_value(
            request.form,
            "monthly_report_day",
            1,
            1,
            28,
        )

        preferences.daily_checkup_time = _time_value(
            request.form,
            "daily_checkup_time",
            preferences.daily_checkup_time,
        )
        preferences.weekly_summary_time = _time_value(
            request.form,
            "weekly_summary_time",
            preferences.weekly_summary_time,
        )
        preferences.monthly_report_time = _time_value(
            request.form,
            "monthly_report_time",
            preferences.monthly_report_time,
        )
        preferences.quiet_hours_start = _optional_time_value(
            request.form,
            "quiet_hours_start",
        )
        preferences.quiet_hours_end = _optional_time_value(
            request.form,
            "quiet_hours_end",
        )

        try:
            db.session.commit()
            flash("Notification preferences saved successfully.", "success")
        except Exception as error:
            db.session.rollback()
            print("Notification settings error:", error)
            flash("Notification settings could not be saved.", "error")

        return redirect(url_for("notification_bp.notification_settings"))

    recent_logs = (
        EmailNotificationLog.query
        .filter_by(user_id=current_user.id)
        .order_by(EmailNotificationLog.sent_at.desc())
        .limit(8)
        .all()
    )

    return render_template(
        "notification_settings.html",
        preferences=preferences,
        recent_logs=recent_logs,
        email_configured=email_is_configured(),
    )


@notification_bp.route("/notifications/history")
@login_required
def notification_history():
    logs = (
        EmailNotificationLog.query
        .filter_by(user_id=current_user.id)
        .order_by(EmailNotificationLog.sent_at.desc())
        .limit(100)
        .all()
    )

    return render_template(
        "notification_history.html",
        logs=logs,
    )


@notification_bp.route("/notifications/email/test", methods=["POST"])
@login_required
def send_test_notification_email():
    if not email_is_configured():
        flash(
            "Email is not configured yet. Add MAIL settings to your .env file.",
            "error",
        )
        return redirect(url_for("notification_bp.notification_settings"))

    try:
        send_test_email(current_user)
        flash("Test email sent successfully.", "success")

    except Exception as error:
        print("Test email error:", error)
        flash("Test email could not be sent. Check your email settings.", "error")

    return redirect(request.referrer or url_for("dashboard"))


@notification_bp.route("/notifications/email/check", methods=["POST"])
@login_required
def run_my_email_notification_check():
    if not email_is_configured():
        flash(
            "Email is not configured yet. Add MAIL settings to your .env file.",
            "error",
        )
        return redirect(url_for("notification_bp.notification_settings"))

    try:
        result = run_email_notification_check(
            user_id=current_user.id,
            include_automatic_summaries=True,
        )

        flash(
            (
                "Email check finished: "
                f"{result['custom_reminders_sent']} custom reminder(s), "
                f"{result['deadline_reminders_sent']} deadline reminder(s), "
                f"{result['daily_summaries_sent']} daily checkup(s), "
                f"{result['weekly_summaries_sent']} weekly summary email(s), "
                f"{result['monthly_reports_sent']} monthly report(s)."
            ),
            "success",
        )

    except Exception as error:
        print("Email check error:", error)
        flash("Email notification check failed.", "error")

    return redirect(request.referrer or url_for("dashboard"))


@notification_bp.route("/notifications/email/daily-summary", methods=["POST"])
@login_required
def send_my_daily_summary():
    if not email_is_configured():
        flash(
            "Email is not configured yet. Add MAIL settings to your .env file.",
            "error",
        )
        return redirect(url_for("notification_bp.notification_settings"))

    try:
        was_sent = send_daily_summary_email(current_user, force=True)

        if was_sent:
            flash("Daily checkup email sent successfully.", "success")
        else:
            flash("Daily checkup was already sent today.", "info")

    except Exception as error:
        print("Daily summary email error:", error)
        flash("Daily checkup email could not be sent.", "error")

    return redirect(request.referrer or url_for("dashboard"))


@notification_bp.route("/notifications/email/weekly-summary", methods=["POST"])
@login_required
def send_my_weekly_summary():
    if not email_is_configured():
        flash(
            "Email is not configured yet. Add MAIL settings to your .env file.",
            "error",
        )
        return redirect(url_for("notification_bp.notification_settings"))

    try:
        was_sent = send_weekly_summary_email(current_user, force=True)

        if was_sent:
            flash("Weekly summary email sent successfully.", "success")
        else:
            flash("Weekly summary was already sent this week.", "info")

    except Exception as error:
        print("Weekly summary email error:", error)
        flash("Weekly summary email could not be sent.", "error")

    return redirect(request.referrer or url_for("dashboard"))


@notification_bp.route("/notifications/email/monthly-analytics", methods=["POST"])
@login_required
def send_my_monthly_analytics():
    if not email_is_configured():
        flash(
            "Email is not configured yet. Add MAIL settings to your .env file.",
            "error",
        )
        return redirect(url_for("notification_bp.notification_settings"))

    try:
        was_sent = send_monthly_analytics_email(current_user, force=True)

        if was_sent:
            flash("Monthly analytics email sent successfully.", "success")
        else:
            flash("Monthly analytics email was already sent this month.", "info")

    except Exception as error:
        print("Monthly analytics email error:", error)
        flash("Monthly analytics email could not be sent.", "error")

    return redirect(request.referrer or url_for("dashboard"))

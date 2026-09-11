"""Notification preference parsing and persistence for LifeOS."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import EmailNotificationLog, NotificationPreference, User
from services.notification_service import get_or_create_notification_preferences


TRUE_FORM_VALUES = {"on", "true", "1", "yes"}


class NotificationPreferencePersistenceError(RuntimeError):
    """Raised when notification preferences cannot be saved."""


def _checkbox_enabled(form: Mapping[str, Any], name: str) -> bool:
    return str(form.get(name) or "").lower() in TRUE_FORM_VALUES


def _int_value(
    form: Mapping[str, Any],
    name: str,
    default: int,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    try:
        value = int(form.get(name, default))
    except (TypeError, ValueError):
        value = default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def _time_value(form: Mapping[str, Any], name: str, default):
    raw_value = form.get(name)
    if not raw_value:
        return default
    try:
        return datetime.strptime(str(raw_value), "%H:%M").time()
    except ValueError:
        return default


def _optional_time_value(form: Mapping[str, Any], name: str):
    raw_value = form.get(name)
    if not raw_value:
        return None
    try:
        return datetime.strptime(str(raw_value), "%H:%M").time()
    except ValueError:
        return None


def update_notification_preferences(
    user: User,
    form: Mapping[str, Any],
) -> NotificationPreference:
    preferences = get_or_create_notification_preferences(user)

    boolean_fields = (
        "email_enabled",
        "task_reminders_enabled",
        "custom_task_reminders_enabled",
        "overdue_alerts_enabled",
        "project_deadline_alerts_enabled",
        "project_risk_alerts_enabled",
        "daily_checkup_enabled",
        "weekly_summary_enabled",
        "monthly_analytics_enabled",
    )
    for field in boolean_fields:
        setattr(preferences, field, _checkbox_enabled(form, field))

    preferences.task_reminder_days_before = _int_value(
        form,
        "task_reminder_days_before",
        1,
        0,
        14,
    )
    preferences.project_reminder_days_before = _int_value(
        form,
        "project_reminder_days_before",
        3,
        0,
        30,
    )
    preferences.weekly_summary_day = _int_value(
        form,
        "weekly_summary_day",
        6,
        0,
        6,
    )
    preferences.monthly_report_day = _int_value(
        form,
        "monthly_report_day",
        1,
        1,
        28,
    )

    preferences.daily_checkup_time = _time_value(
        form,
        "daily_checkup_time",
        preferences.daily_checkup_time,
    )
    preferences.weekly_summary_time = _time_value(
        form,
        "weekly_summary_time",
        preferences.weekly_summary_time,
    )
    preferences.monthly_report_time = _time_value(
        form,
        "monthly_report_time",
        preferences.monthly_report_time,
    )
    preferences.quiet_hours_start = _optional_time_value(
        form,
        "quiet_hours_start",
    )
    preferences.quiet_hours_end = _optional_time_value(
        form,
        "quiet_hours_end",
    )

    try:
        db.session.commit()
        return preferences
    except SQLAlchemyError as error:
        db.session.rollback()
        raise NotificationPreferencePersistenceError from error


def recent_notification_logs(user_id: int, limit: int = 8):
    return (
        EmailNotificationLog.query.filter_by(user_id=user_id)
        .order_by(EmailNotificationLog.sent_at.desc())
        .limit(limit)
        .all()
    )

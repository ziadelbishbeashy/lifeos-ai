"""Notification-preference service tests."""

from database import db
from models import NotificationPreference, User
from services.notification_preferences_service import (
    update_notification_preferences,
)


def test_notification_preferences_are_normalized(app, user):
    with app.app_context():
        account = db.session.get(User, user)
        preferences = update_notification_preferences(
            account,
            {
                "email_enabled": "on",
                "task_reminders_enabled": "on",
                "task_reminder_days_before": "99",
                "project_reminder_days_before": "-3",
                "weekly_summary_day": "9",
                "monthly_report_day": "0",
                "daily_checkup_time": "09:15",
            },
        )
        assert preferences.email_enabled is True
        assert preferences.task_reminder_days_before == 14
        assert preferences.project_reminder_days_before == 0
        assert preferences.weekly_summary_day == 6
        assert preferences.monthly_report_day == 1
        assert NotificationPreference.query.filter_by(user_id=user).count() == 1

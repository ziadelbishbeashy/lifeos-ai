import os
import threading
import time

from services.email_service import email_is_configured
from services.notification_service import run_email_notification_check


_scheduler_started = False


def _env_bool(name, default=False):
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def _run_scheduler_check(app):
    """Run one notification check safely inside the Flask app context."""

    with app.app_context():
        try:
            if not email_is_configured():
                app.logger.warning(
                    "LifeOS email scheduler skipped: email is not configured."
                )
                return

            result = run_email_notification_check(
                include_automatic_summaries=True
            )

            app.logger.info(
                "LifeOS email scheduler completed: %s",
                result,
            )

        except Exception as error:
            app.logger.exception(
                "LifeOS email scheduler error: %s",
                error,
            )


def _scheduler_loop(app, interval_minutes):
    with app.app_context():
        app.logger.info(
            "LifeOS email scheduler started. Interval: %s minute(s).",
            interval_minutes,
        )

    # Important for testing and real reminders:
    # Run once immediately after Flask starts, then wait for the interval.
    # The old version slept first, so a reminder could wait 15+ minutes.
    while True:
        _run_scheduler_check(app)
        time.sleep(interval_minutes * 60)


def start_notification_scheduler(app):
    global _scheduler_started

    if _scheduler_started:
        return False

    if not _env_bool("ENABLE_EMAIL_SCHEDULER", False):
        app.logger.info("LifeOS email scheduler is disabled by .env.")
        return False

    try:
        interval_minutes = int(
            os.getenv("EMAIL_SCHEDULER_INTERVAL_MINUTES", "60")
        )
    except (TypeError, ValueError):
        interval_minutes = 60

    # Allow 1-minute checks while developing/testing.
    # Later, production can use 15, 30, or 60 minutes.
    interval_minutes = max(1, interval_minutes)

    thread = threading.Thread(
        target=_scheduler_loop,
        args=(app, interval_minutes),
        daemon=True,
    )

    thread.start()
    _scheduler_started = True

    return True

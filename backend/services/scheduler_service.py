"""Local scheduler compatibility layer.

Public deployments should run ``python -m workers.notification_worker`` as a
separate process. The in-process thread is retained only for local development.
"""

from __future__ import annotations

import threading
import time

from services.email_service import email_is_configured
from services.notification_service import run_email_notification_check


_scheduler_started = False
_scheduler_lock = threading.Lock()


def run_notification_check_once(app, user_id: int | None = None):
    """Run one email-notification pass inside the application context."""

    with app.app_context():
        if not email_is_configured():
            app.logger.warning(
                "LifeOS email notification check skipped: email is not configured."
            )
            return {
                "skipped": True,
                "reason": "email_not_configured",
            }

        result = run_email_notification_check(
            user_id=user_id,
            include_automatic_summaries=True,
        )
        app.logger.info("LifeOS email notification check completed: %s", result)
        return result


def _scheduler_loop(app, interval_minutes: int) -> None:
    app.logger.info(
        "Local LifeOS email scheduler started at a %s-minute interval.",
        interval_minutes,
    )
    while True:
        try:
            run_notification_check_once(app)
        except Exception:
            app.logger.exception("LifeOS local email scheduler failed.")
        time.sleep(interval_minutes * 60)


def start_notification_scheduler(app) -> bool:
    """Start the local-only scheduler once and return whether it started."""

    global _scheduler_started

    if not app.config.get("ENABLE_EMAIL_SCHEDULER", False):
        app.logger.info("LifeOS local email scheduler is disabled.")
        return False

    if app.config.get("ENV_NAME") == "production":
        app.logger.warning(
            "The in-process scheduler is disabled in production. "
            "Run workers.notification_worker separately."
        )
        return False

    with _scheduler_lock:
        if _scheduler_started:
            return False
        try:
            interval_minutes = int(
                app.config.get("EMAIL_SCHEDULER_INTERVAL_MINUTES", 60)
            )
        except (TypeError, ValueError):
            interval_minutes = 60
        interval_minutes = max(1, interval_minutes)

        thread = threading.Thread(
            target=_scheduler_loop,
            args=(app, interval_minutes),
            daemon=True,
            name="lifeos-email-scheduler",
        )
        thread.start()
        _scheduler_started = True
        return True

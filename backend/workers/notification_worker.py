"""Standalone notification worker for production or local testing."""

from __future__ import annotations

import time

from app import create_app
from services.scheduler_service import run_notification_check_once


def main() -> None:
    app = create_app()
    interval = max(
        1,
        int(app.config.get("EMAIL_SCHEDULER_INTERVAL_MINUTES", 60)),
    )
    app.logger.info(
        "LifeOS notification worker started at a %s-minute interval.",
        interval,
    )
    while True:
        try:
            run_notification_check_once(app)
        except Exception:
            app.logger.exception("LifeOS notification worker cycle failed.")
        time.sleep(interval * 60)


if __name__ == "__main__":
    main()

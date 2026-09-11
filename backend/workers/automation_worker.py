"""I17 background automation worker.

Run as a separate process from the Flask web server.  The worker executes only
reviewed, read-only intelligence actions and creates audit / notification
metadata.  It never performs direct Project/Task/Note/Document mutations.
"""

from __future__ import annotations

import time

from app import create_app
from models import User
from services.automation_engine_service import execute_owned_automation_cycle


def run_automation_pass(app) -> dict:
    with app.app_context():
        users = User.query.order_by(User.id.asc()).all()
        candidates = 0
        executed = 0
        failed = 0
        notifications = 0
        for user in users:
            cycle = execute_owned_automation_cycle(owner_id=user.id)
            candidates += len(cycle.candidates)
            executed += len(cycle.results)
            failed += len(cycle.failures)
            notifications += sum(1 for item in cycle.results if item.notification_event_id is not None)
            if cycle.candidates or cycle.failures:
                app.logger.info(
                    "I17 automation cycle user=%s candidates=%s executed=%s failed=%s notifications=%s",
                    user.id,
                    len(cycle.candidates),
                    len(cycle.results),
                    len(cycle.failures),
                    sum(1 for item in cycle.results if item.notification_event_id is not None),
                )
        return {
            "users_scanned": len(users),
            "candidates": candidates,
            "executed": executed,
            "failed": failed,
            "notifications_prepared": notifications,
            "workspace_mutation": False,
        }


def main() -> None:
    app = create_app()
    interval = max(60, int(app.config.get("LIFEOS_AUTOMATION_POLL_SECONDS", 60)))
    if not app.config.get("ENABLE_LIFEOS_AUTOMATIONS", False):
        app.logger.warning(
            "LifeOS automation worker is disabled. Set ENABLE_LIFEOS_AUTOMATIONS=true to activate I17 background intelligence."
        )
        return

    app.logger.info(
        "I17 automation worker started (poll=%ss). Workspace mutation remains disabled; I9 confirmation is still required.",
        interval,
    )
    while True:
        try:
            run_automation_pass(app)
        except Exception:
            app.logger.exception("LifeOS automation pass failed.")
        time.sleep(interval)


if __name__ == "__main__":
    main()

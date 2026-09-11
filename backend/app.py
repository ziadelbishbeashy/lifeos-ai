"""Compatibility entry point for LifeOS Foundation V2.

Existing commands such as ``python -m flask --app app`` and imports such as
``from app import create_app`` continue to work. The real application factory
now lives in ``lifeos.application``.
"""

from __future__ import annotations

import os

from lifeos.application import create_app
from lifeos.core.database import db
from services.scheduler_service import start_notification_scheduler


__all__ = ["create_app"]


if __name__ == "__main__":
    app = create_app()

    if app.config.get("AUTO_CREATE_DB"):
        with app.app_context():
            db.create_all()

    if app.config.get("ENABLE_EMAIL_SCHEDULER"):
        start_notification_scheduler(app)

    if os.getenv("SHOW_REGISTERED_ROUTES", "false").lower() == "true":
        print("\nREGISTERED ROUTES:")
        for rule in app.url_map.iter_rules():
            print(rule)

    app.run(debug=bool(app.config.get("DEBUG")), use_reloader=False)

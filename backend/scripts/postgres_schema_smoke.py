"""Create/drop the current model schema on a disposable PostgreSQL database.

Use only against a disposable database. This is a portability smoke test, not a
production migration mechanism.
"""

from __future__ import annotations

import os

from sqlalchemy import text

from app import create_app
from database import db, normalize_database_uri


def main() -> int:
    url = normalize_database_uri(os.getenv("POSTGRES_SMOKE_DATABASE_URL") or "")
    if not url:
        raise SystemExit("POSTGRES_SMOKE_DATABASE_URL is required.")

    app = create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": url,
            "WTF_CSRF_ENABLED": False,
        },
    )

    with app.app_context():
        db.drop_all()
        db.create_all()
        value = db.session.execute(text("SELECT 1")).scalar_one()
        if value != 1:
            raise RuntimeError("PostgreSQL smoke query failed.")
        db.drop_all()

    print("PostgreSQL schema smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

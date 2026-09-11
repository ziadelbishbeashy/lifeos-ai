"""Liveness and readiness checks for public deployment."""

from __future__ import annotations

from sqlalchemy import text

from database import db


def database_is_ready() -> bool:
    try:
        db.session.execute(text("SELECT 1"))
        return True
    except Exception:
        db.session.rollback()
        return False

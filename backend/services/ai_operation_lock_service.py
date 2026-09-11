"""Database-backed idempotency locks for expensive LifeOS AI operations.

The table is intentionally tiny and transient. A unique lock key protects the
same owned resource/operation across browser double-clicks, retries, tabs and
multiple Flask workers. Expiry prevents a crashed worker from blocking forever.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError

from database import db
from models import AIOperationLock


class AIOperationLockError(RuntimeError):
    """Base error for AI operation locking."""


class AIOperationAlreadyRunningError(AIOperationLockError):
    """Raised when an equivalent operation already owns the lock."""


@dataclass(frozen=True)
class AIOperationLockHandle:
    lock_key: str
    operation: str
    resource_type: str
    resource_id: int


def _safe_identity(value: str, *, fallback: str) -> str:
    cleaned = str(value or "").strip().lower()
    return cleaned or fallback


def build_ai_operation_lock_key(
    *,
    user_id: int,
    operation: str,
    resource_type: str,
    resource_id: int,
) -> str:
    """Build a stable opaque key without persisting user-facing text."""

    raw = "|".join(
        [
            str(int(user_id)),
            _safe_identity(operation, fallback="unknown"),
            _safe_identity(resource_type, fallback="resource"),
            str(int(resource_id)),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sqlite_execute(statements) -> list:
    """Execute lock statements through the scoped session in SQLite tests.

    ``sqlite:///:memory:`` is connection-local, so a second engine transaction
    may see a different empty database. Production MSSQL uses the independent
    engine transaction path below. Lock callers acquire before workspace writes,
    so this testing compatibility path cannot confirm an AI-generated mutation.
    """

    results = []
    try:
        for statement in statements:
            results.append(db.session.execute(statement))
        db.session.commit()
        return results
    except Exception:
        db.session.rollback()
        raise


def _execute_lock_transaction(statements) -> list:
    if db.engine.dialect.name == "sqlite":
        return _sqlite_execute(statements)
    results = []
    with db.engine.begin() as connection:
        for statement in statements:
            results.append(connection.execute(statement))
    return results


def acquire_ai_operation_lock(
    *,
    user_id: int,
    operation: str,
    resource_type: str,
    resource_id: int,
    fingerprint: str | None = None,
    ttl_seconds: int = 900,
) -> AIOperationLockHandle:
    """Atomically acquire a cross-worker lock or report that work is running."""

    safe_ttl = max(30, min(int(ttl_seconds or 900), 60 * 60))
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=safe_ttl)
    key = build_ai_operation_lock_key(
        user_id=user_id,
        operation=operation,
        resource_type=resource_type,
        resource_id=resource_id,
    )

    values = {
        "lock_key": key,
        "user_id": int(user_id),
        "operation": _safe_identity(operation, fallback="unknown")[:80],
        "resource_type": _safe_identity(resource_type, fallback="resource")[:40],
        "resource_id": int(resource_id),
        "fingerprint": str(fingerprint or "")[:64] or None,
        "acquired_at": now,
        "expires_at": expires_at,
    }

    try:
        _execute_lock_transaction(
            [
                delete(AIOperationLock.__table__).where(
                    AIOperationLock.lock_key == key,
                    AIOperationLock.expires_at <= now,
                ),
                insert(AIOperationLock.__table__).values(**values),
            ]
        )
    except IntegrityError as error:
        raise AIOperationAlreadyRunningError(
            "This operation is already running."
        ) from error

    return AIOperationLockHandle(
        lock_key=key,
        operation=values["operation"],
        resource_type=values["resource_type"],
        resource_id=int(resource_id),
    )


def release_ai_operation_lock(handle: AIOperationLockHandle) -> None:
    """Release a lock without touching workspace content."""

    try:
        _execute_lock_transaction(
            [
                delete(AIOperationLock.__table__).where(
                    AIOperationLock.lock_key == handle.lock_key
                )
            ]
        )
    except Exception:
        # Locks expire. A cleanup failure must never replace the actual result.
        return


def is_ai_operation_running(
    *,
    user_id: int,
    operation: str,
    resource_type: str,
    resource_id: int,
) -> bool:
    """Return whether a non-expired lock currently protects this operation."""

    now = datetime.utcnow()
    key = build_ai_operation_lock_key(
        user_id=user_id,
        operation=operation,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    try:
        results = _execute_lock_transaction(
            [
                delete(AIOperationLock.__table__).where(
                    AIOperationLock.lock_key == key,
                    AIOperationLock.expires_at <= now,
                ),
                select(AIOperationLock.id).where(
                    AIOperationLock.lock_key == key,
                    AIOperationLock.expires_at > now,
                ),
            ]
        )
        row = results[-1].first()
        return row is not None
    except Exception:
        # Lock status must never make a read-only detail page fail.
        return False


@contextmanager
def ai_operation_lock(**kwargs):
    """Context manager that always releases the acquired operation lock."""

    handle = acquire_ai_operation_lock(**kwargs)
    try:
        yield handle
    finally:
        release_ai_operation_lock(handle)

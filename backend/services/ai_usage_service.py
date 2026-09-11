"""LifeOS-owned AI usage ledger and user-scoped usage reporting."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

try:
    from flask import current_app, has_app_context, has_request_context, request
    from flask_login import current_user
except Exception:  # pragma: no cover - keeps static tooling import-safe.
    current_app = None  # type: ignore[assignment]
    request = None  # type: ignore[assignment]
    current_user = None  # type: ignore[assignment]

    def has_app_context() -> bool:
        return False

    def has_request_context() -> bool:
        return False

from ai.providers.base import ProviderUsage
from services.ai_pricing_service import UsageCost


def _enabled() -> bool:
    value = os.getenv("AI_USAGE_LEDGER_ENABLED", "true")
    if has_app_context() and current_app is not None:
        # Existing tests use an in-memory SQLite database where a second engine
        # transaction can share the same underlying connection. Keep telemetry
        # off by default in TESTING so metering never changes workspace tests.
        if current_app.config.get("TESTING") and "AI_USAGE_LEDGER_ENABLED" not in current_app.config:
            return False
        value = current_app.config.get("AI_USAGE_LEDGER_ENABLED", value)
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _current_user_id() -> int | None:
    if not has_request_context() or current_user is None:
        return None
    try:
        if current_user.is_authenticated:
            return int(current_user.id)
    except Exception:
        return None
    return None


def _request_metadata() -> tuple[str, str | None]:
    if not has_request_context() or request is None:
        return f"internal-{uuid.uuid4().hex}", None
    environ = request.environ
    request_id = str(environ.get("lifeos.ai_request_id") or "").strip()
    if not request_id:
        request_id = (request.headers.get("X-Request-ID") or uuid.uuid4().hex).strip()
        environ["lifeos.ai_request_id"] = request_id
    endpoint = str(getattr(request, "endpoint", None) or "").strip() or None
    return request_id[:64], endpoint[:160] if endpoint else None


def _persist_usage(
    *,
    operation: str,
    provider: str,
    model: str,
    feature: str,
    prompt_characters: int,
    provider_call_index: int,
    usage: ProviderUsage,
    cost: UsageCost,
    latency_ms: int,
    success: bool,
    error_category: str | None = None,
    langsmith_run_id: str | None = None,
    user_id: int | None = None,
) -> None:
    """Persist one provider attempt without affecting workspace transactions."""

    if not _enabled() or not has_app_context():
        return

    request_id, endpoint = _request_metadata()
    resolved_user_id = int(user_id) if user_id is not None else _current_user_id()
    values = {
        "user_id": resolved_user_id,
        "request_id": request_id,
        "endpoint": endpoint,
        "feature": str(feature or "unknown")[:80],
        "operation": str(operation or "unknown")[:32],
        "provider": str(provider or "unknown")[:40],
        "model": str(model or "unknown")[:120],
        "provider_call_index": max(1, int(provider_call_index or 1)),
        "prompt_characters": max(0, int(prompt_characters or 0)),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "thinking_tokens": usage.thinking_tokens,
        "cached_input_tokens": usage.cached_input_tokens,
        "total_tokens": usage.total_tokens,
        "input_cost_usd": cost.input_cost_usd,
        "output_cost_usd": cost.output_cost_usd,
        "total_cost_usd": cost.total_cost_usd,
        "pricing_source": cost.pricing_source,
        "latency_ms": max(0, int(latency_ms or 0)),
        "success": bool(success),
        "error_category": str(error_category or "")[:80] or None,
        "langsmith_run_id": str(langsmith_run_id or "")[:80] or None,
        "usage_json": json.dumps(usage.raw or {}, ensure_ascii=False, sort_keys=True),
        "created_at": datetime.utcnow(),
    }

    try:
        from database import db
        from models import AIUsageEvent

        # Never use db.session.commit() here: that could commit a workspace write
        # merely because an AI call was metered. Use an independent transaction.
        with db.engine.begin() as connection:
            connection.execute(AIUsageEvent.__table__.insert().values(**values))
    except Exception as error:  # pragma: no cover - telemetry failure is non-fatal.
        if current_app is not None:
            current_app.logger.warning(
                "lifeos.ai_usage_persist_failed operation=%s error=%s",
                str(operation or "unknown")[:32],
                str(error)[:300],
            )


def record_generation_usage(
    *,
    provider: str,
    model: str,
    feature: str,
    prompt_characters: int,
    provider_call_index: int,
    usage: ProviderUsage,
    cost: UsageCost,
    latency_ms: int,
    success: bool,
    error_category: str | None = None,
    langsmith_run_id: str | None = None,
    user_id: int | None = None,
) -> None:
    _persist_usage(
        operation="generation",
        provider=provider,
        model=model,
        feature=feature,
        prompt_characters=prompt_characters,
        provider_call_index=provider_call_index,
        usage=usage,
        cost=cost,
        latency_ms=latency_ms,
        success=success,
        error_category=error_category,
        langsmith_run_id=langsmith_run_id,
        user_id=user_id,
    )


def record_embedding_usage(
    *,
    provider: str,
    model: str,
    feature: str,
    prompt_characters: int,
    provider_call_index: int,
    usage: ProviderUsage,
    cost: UsageCost,
    latency_ms: int,
    success: bool,
    error_category: str | None = None,
    langsmith_run_id: str | None = None,
    user_id: int | None = None,
) -> None:
    _persist_usage(
        operation="embedding",
        provider=provider,
        model=model,
        feature=feature,
        prompt_characters=prompt_characters,
        provider_call_index=provider_call_index,
        usage=usage,
        cost=cost,
        latency_ms=latency_ms,
        success=success,
        error_category=error_category,
        langsmith_run_id=langsmith_run_id,
        user_id=user_id,
    )


def _money(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(Decimal(value))
    except Exception:
        return None


def serialize_usage_event(event) -> dict[str, Any]:
    return {
        "id": event.id,
        "request_id": event.request_id,
        "endpoint": event.endpoint,
        "feature": event.feature,
        "operation": event.operation,
        "provider": event.provider,
        "model": event.model,
        "provider_call_index": event.provider_call_index,
        "prompt_characters": event.prompt_characters,
        "input_tokens": event.input_tokens,
        "output_tokens": event.output_tokens,
        "thinking_tokens": event.thinking_tokens,
        "cached_input_tokens": event.cached_input_tokens,
        "total_tokens": event.total_tokens,
        "input_cost_usd": _money(event.input_cost_usd),
        "output_cost_usd": _money(event.output_cost_usd),
        "total_cost_usd": _money(event.total_cost_usd),
        "pricing_source": event.pricing_source,
        "latency_ms": event.latency_ms,
        "success": bool(event.success),
        "error_category": event.error_category,
        "langsmith_run_id": event.langsmith_run_id,
        "created_at": event.created_at.isoformat() + "Z" if event.created_at else None,
    }


def list_owned_usage_events(*, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    from models import AIUsageEvent

    safe_limit = min(200, max(1, int(limit or 50)))
    rows = (
        AIUsageEvent.query.filter_by(user_id=int(user_id))
        .order_by(AIUsageEvent.created_at.desc(), AIUsageEvent.id.desc())
        .limit(safe_limit)
        .all()
    )
    return [serialize_usage_event(row) for row in rows]


def summarize_owned_usage(*, user_id: int, days: int = 30) -> dict[str, Any]:
    from models import AIUsageEvent

    safe_days = min(365, max(1, int(days or 30)))
    since = datetime.utcnow() - timedelta(days=safe_days)
    rows = (
        AIUsageEvent.query.filter(
            AIUsageEvent.user_id == int(user_id),
            AIUsageEvent.created_at >= since,
        )
        .order_by(AIUsageEvent.created_at.asc())
        .all()
    )

    totals = {
        "calls": 0,
        "generation_calls": 0,
        "embedding_calls": 0,
        "successful_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "thinking_tokens": 0,
        "cached_input_tokens": 0,
        "total_tokens": 0,
        "known_cost_usd": Decimal("0"),
        "calls_with_known_cost": 0,
    }
    features: dict[str, dict[str, Any]] = {}
    request_operations: dict[str, dict[str, Any]] = {}

    for row in rows:
        totals["calls"] += 1
        if row.operation == "generation":
            totals["generation_calls"] += 1
        elif row.operation == "embedding":
            totals["embedding_calls"] += 1
        totals["successful_calls"] += 1 if row.success else 0
        for key in (
            "input_tokens", "output_tokens", "thinking_tokens",
            "cached_input_tokens", "total_tokens",
        ):
            totals[key] += max(0, int(getattr(row, key) or 0))
        if row.total_cost_usd is not None:
            totals["known_cost_usd"] += Decimal(row.total_cost_usd)
            totals["calls_with_known_cost"] += 1

        feature = str(row.feature or "unknown")
        bucket = features.setdefault(
            feature,
            {
                "calls": 0,
                "total_tokens": 0,
                "thinking_tokens": 0,
                "known_cost_usd": Decimal("0"),
                "calls_with_known_cost": 0,
                "operations": set(),
                "models": set(),
            },
        )
        bucket["calls"] += 1
        bucket["operations"].add(str(row.operation or "unknown"))
        bucket["models"].add(str(row.model or "unknown"))
        bucket["total_tokens"] += max(0, int(row.total_tokens or 0))
        bucket["thinking_tokens"] += max(0, int(row.thinking_tokens or 0))
        if row.total_cost_usd is not None:
            bucket["known_cost_usd"] += Decimal(row.total_cost_usd)
            bucket["calls_with_known_cost"] += 1

        request_key = str(row.request_id or f"event-{row.id}")
        operation_bucket = request_operations.setdefault(
            request_key,
            {
                "request_id": request_key,
                "endpoint": str(row.endpoint or "internal"),
                "calls": 0,
                "successful_calls": 0,
                "calls_with_known_cost": 0,
                "total_tokens": 0,
                "thinking_tokens": 0,
                "known_cost_usd": Decimal("0"),
                "features": set(),
                "models": set(),
                "created_at": row.created_at,
            },
        )
        operation_bucket["calls"] += 1
        operation_bucket["successful_calls"] += 1 if row.success else 0
        operation_bucket["total_tokens"] += max(0, int(row.total_tokens or 0))
        operation_bucket["thinking_tokens"] += max(0, int(row.thinking_tokens or 0))
        operation_bucket["features"].add(feature)
        operation_bucket["models"].add(str(row.model or "unknown"))
        if row.total_cost_usd is not None:
            operation_bucket["known_cost_usd"] += Decimal(row.total_cost_usd)
            operation_bucket["calls_with_known_cost"] += 1
        if row.created_at and (operation_bucket["created_at"] is None or row.created_at < operation_bucket["created_at"]):
            operation_bucket["created_at"] = row.created_at

    feature_rows = [
        {
            "feature": name,
            "operations": sorted(data["operations"]),
            "models": sorted(data["models"]),
            "calls": data["calls"],
            "total_tokens": data["total_tokens"],
            "thinking_tokens": data["thinking_tokens"],
            "known_cost_usd": float(data["known_cost_usd"]),
            "average_tokens_per_call": (
                round(data["total_tokens"] / data["calls"], 2) if data["calls"] else 0
            ),
            "average_thinking_tokens_per_call": (
                round(data["thinking_tokens"] / data["calls"], 2) if data["calls"] else 0
            ),
            "average_known_cost_usd": (
                float(data["known_cost_usd"] / data["calls_with_known_cost"])
                if data["calls_with_known_cost"] else None
            ),
        }
        for name, data in features.items()
    ]
    feature_rows.sort(
        key=lambda item: (-item["known_cost_usd"], -item["total_tokens"], item["feature"])
    )

    operation_rows: list[dict[str, Any]] = []
    complete_operation_cost = Decimal("0")
    complete_operation_count = 0
    for data in request_operations.values():
        # A successful provider call without cost means the operation total is
        # only partial (for example an embedding whose token count is missing).
        successful_unmetered = max(0, data["successful_calls"] - data["calls_with_known_cost"])
        cost_complete = successful_unmetered == 0
        if cost_complete and data["successful_calls"]:
            complete_operation_cost += data["known_cost_usd"]
            complete_operation_count += 1
        operation_rows.append(
            {
                "request_id": data["request_id"],
                "endpoint": data["endpoint"],
                "features": sorted(data["features"]),
                "models": sorted(data["models"]),
                "calls": data["calls"],
                "total_tokens": data["total_tokens"],
                "thinking_tokens": data["thinking_tokens"],
                "known_cost_usd": float(data["known_cost_usd"]),
                "cost_complete": cost_complete,
                "created_at": data["created_at"].isoformat() + "Z" if data["created_at"] else None,
            }
        )
    operation_rows.sort(key=lambda item: item["created_at"] or "", reverse=True)

    operation_count = len(request_operations)
    return {
        "days": safe_days,
        "since": since.isoformat() + "Z",
        "totals": {
            **{key: value for key, value in totals.items() if key != "known_cost_usd"},
            "known_cost_usd": float(totals["known_cost_usd"]),
            "average_known_cost_usd": (
                float(totals["known_cost_usd"] / totals["calls_with_known_cost"])
                if totals["calls_with_known_cost"] else None
            ),
            "operations": operation_count,
            "operations_with_complete_cost": complete_operation_count,
            "average_tokens_per_operation": (
                round(totals["total_tokens"] / operation_count, 2) if operation_count else 0
            ),
            "average_complete_operation_cost_usd": (
                float(complete_operation_cost / complete_operation_count)
                if complete_operation_count else None
            ),
        },
        "by_feature": feature_rows,
        "recent_operations": operation_rows[:30],
    }

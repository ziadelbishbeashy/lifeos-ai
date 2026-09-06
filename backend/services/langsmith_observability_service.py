"""Optional, privacy-conscious LangSmith observability for LifeOS.

LifeOS keeps its own AI usage ledger as the business/accounting source of truth.
LangSmith is a developer observability copy only. Traces intentionally contain
metadata, counts, timings and token/cost usage -- never raw prompts, document
text, questions, or generated answers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Generic, Mapping, TypeVar

try:
    from flask import has_request_context, request
except Exception:  # pragma: no cover - static tooling/import safety
    request = None  # type: ignore[assignment]

    def has_request_context() -> bool:
        return False

T = TypeVar("T")


@dataclass(frozen=True)
class LangSmithTraceResult:
    generation: Any
    run_id: str | None = None


@dataclass(frozen=True)
class LangSmithEmbeddingTraceResult(Generic[T]):
    response: T
    usage: Any
    run_id: str | None = None


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _sampling_rate() -> float:
    try:
        value = float(os.getenv("LANGSMITH_TRACING_SAMPLING_RATE", "1"))
    except (TypeError, ValueError):
        value = 1.0
    return max(0.0, min(1.0, value))


def _sdk_available() -> bool:
    try:
        import langsmith  # noqa: F401
        return True
    except Exception:
        return False


def _requested() -> bool:
    return _bool_env("LANGSMITH_TRACING", False)


def _ready() -> bool:
    return _requested() and bool((os.getenv("LANGSMITH_API_KEY") or "").strip()) and _sdk_available()


def _request_id() -> str | None:
    if not has_request_context() or request is None:
        return None
    try:
        value = str(request.environ.get("lifeos.ai_request_id") or request.headers.get("X-Request-ID") or "").strip()
    except Exception:
        return None
    return value[:64] or None


def _safe_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:160]
    return str(value)[:160]


def _safe_metadata(values: Mapping[str, Any] | None) -> dict[str, Any]:
    if not values:
        return {}
    result: dict[str, Any] = {}
    for key, value in values.items():
        safe_key = str(key or "")[:80]
        if not safe_key:
            continue
        if isinstance(value, (list, tuple, set)):
            result[safe_key] = [_safe_scalar(item) for item in list(value)[:20]]
        elif isinstance(value, dict):
            # Keep nested metadata shallow and scalar-only.
            result[safe_key] = {
                str(nested_key)[:80]: _safe_scalar(nested_value)
                for nested_key, nested_value in list(value.items())[:20]
            }
        else:
            result[safe_key] = _safe_scalar(value)
    return result


def _processed_output_metadata(
    output: Any,
    builder: Callable[[Any], Mapping[str, Any] | None] | None,
) -> dict[str, Any]:
    try:
        values = builder(output) if builder is not None else {"result_type": type(output).__name__}
        return {"status": "completed", **_safe_metadata(values)}
    except Exception:
        return {"status": "completed", "result_type": type(output).__name__}


def _base_metadata(*, feature: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "lifeos_feature": str(feature or "unknown")[:80],
        "lifeos_environment": (os.getenv("LIFEOS_ENV") or "development")[:40],
        "content_logged": False,
        "privacy_mode": "metadata_only",
    }
    request_id = _request_id()
    if request_id:
        metadata["lifeos_request_id"] = request_id
    return metadata


def langsmith_status() -> dict[str, Any]:
    """Return non-secret runtime status for the development analytics page."""

    requested = _requested()
    api_key_configured = bool((os.getenv("LANGSMITH_API_KEY") or "").strip())
    sdk_available = _sdk_available()
    if not requested:
        state = "disabled"
    elif not api_key_configured:
        state = "needs_api_key"
    elif not sdk_available:
        state = "sdk_unavailable"
    else:
        state = "enabled"

    return {
        "state": state,
        "tracing_requested": requested,
        "ready": state == "enabled",
        "api_key_configured": api_key_configured,
        "sdk_available": sdk_available,
        "project": (os.getenv("LANGSMITH_PROJECT") or "lifeos-development")[:120],
        "endpoint": (os.getenv("LANGSMITH_ENDPOINT") or "https://api.smith.langchain.com")[:200],
        "workspace_configured": bool((os.getenv("LANGSMITH_WORKSPACE_ID") or "").strip()),
        "sampling_rate": _sampling_rate(),
        "privacy_mode": "metadata_only",
        "raw_content_logged": False,
    }


def trace_lifeos_span(
    *,
    name: str,
    feature: str,
    run_type: str = "chain",
    metadata_builder: Callable[[dict[str, Any]], Mapping[str, Any] | None] | None = None,
    output_metadata_builder: Callable[[Any], Mapping[str, Any] | None] | None = None,
):
    """Decorate a LifeOS operation without exposing its arguments/results.

    The wrapped function is invoked exactly once. If LangSmith cannot initialize,
    the original function executes normally. Nested ``traceable`` provider calls
    automatically become child runs of this operation span.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not _ready():
                return func(*args, **kwargs)

            try:
                from langsmith import traceable, uuid7
            except Exception:
                return func(*args, **kwargs)

            dynamic: dict[str, Any] = {}
            if metadata_builder is not None:
                try:
                    dynamic.update(_safe_metadata(metadata_builder(dict(kwargs))))
                except Exception:
                    # Observability metadata must never affect product behavior.
                    pass
            dynamic.update(_base_metadata(feature=feature))

            state = {"entered": False}

            @traceable(
                name=str(name)[:120],
                run_type=run_type,
                tags=["lifeos", str(feature or "unknown")[:80]],
                metadata={"content_logged": False, "privacy_mode": "metadata_only"},
                process_inputs=lambda _inputs: {"content_logged": False},
                process_outputs=lambda output: _processed_output_metadata(
                    output, output_metadata_builder
                ),
                # Do not copy exception text/tracebacks into the external trace.
                exceptions_to_handle=(Exception,),
            )
            def _traced_call():
                state["entered"] = True
                return func(*args, **kwargs)

            try:
                return _traced_call(
                    langsmith_extra={
                        "run_id": uuid7(),
                        "metadata": dynamic,
                        "tags": ["lifeos-operation"],
                    }
                )
            except Exception:
                # If tracing failed before the product function started, fail open.
                # If the product function started, never retry it: preserve exactly-once
                # execution and re-raise its original failure.
                if state["entered"]:
                    raise
                return func(*args, **kwargs)

        return wrapper

    return decorator


def trace_generation_call(
    *,
    provider: str,
    model: str,
    feature: str,
    prompt_characters: int,
    provider_call: Callable[[], Any],
    model_tier: str | None = None,
    requested_model: str | None = None,
    model_tier_source: str | None = None,
) -> LangSmithTraceResult:
    """Run one generation inside an optional metadata-only LangSmith LLM span."""

    if not _ready():
        return LangSmithTraceResult(generation=provider_call())

    try:
        from langsmith import traceable, uuid7
    except Exception:
        return LangSmithTraceResult(generation=provider_call())

    run_id = uuid7()
    holder: dict[str, Any] = {}
    state = {"provider_attempted": False}

    @traceable(
        name="LifeOS AI generation",
        run_type="llm",
        metadata={
            "ls_provider": str(provider),
            "ls_model_name": str(model),
            "lifeos_feature": str(feature),
            "lifeos_model_tier": str(model_tier or "normal"),
            "lifeos_model_tier_source": str(model_tier_source or "feature_default"),
            "lifeos_requested_model": str(requested_model or model),
            "lifeos_model_routed": bool(requested_model and requested_model != model),
            "prompt_characters": int(prompt_characters),
            "content_logged": False,
            "privacy_mode": "metadata_only",
        },
        tags=["lifeos", str(feature or "unknown")],
        process_inputs=lambda _inputs: {"content_logged": False},
        exceptions_to_handle=(Exception,),
    )
    def _traced_call() -> dict[str, Any]:
        state["provider_attempted"] = True
        generation = provider_call()
        holder["generation"] = generation
        usage_metadata = generation.usage.to_langsmith_usage()
        from services.ai_pricing_service import calculate_usage_cost
        cost = calculate_usage_cost(provider=provider, model=model, usage=generation.usage)
        if cost.input_cost_usd is not None:
            usage_metadata["input_cost"] = float(cost.input_cost_usd)
        if cost.output_cost_usd is not None:
            usage_metadata["output_cost"] = float(cost.output_cost_usd)
        if cost.total_cost_usd is not None:
            usage_metadata["total_cost"] = float(cost.total_cost_usd)
        return {
            "status": "completed",
            "output_characters": len(generation.text or ""),
            "usage_metadata": usage_metadata,
            "content_logged": False,
        }

    try:
        _traced_call(
            langsmith_extra={
                "run_id": run_id,
                "metadata": {
                    **_base_metadata(feature=feature),
                    "lifeos_model_tier": str(model_tier or "normal"),
                    "lifeos_model_tier_source": str(model_tier_source or "feature_default"),
                    "lifeos_requested_model": str(requested_model or model),
                    "lifeos_model_routed": bool(requested_model and requested_model != model),
                },
            }
        )
        generation = holder.get("generation")
        if generation is None:
            return LangSmithTraceResult(generation=provider_call())
        return LangSmithTraceResult(generation=generation, run_id=str(run_id))
    except Exception:
        # Never retry a provider call merely because telemetry failed.
        generation = holder.get("generation")
        if generation is not None:
            return LangSmithTraceResult(generation=generation, run_id=str(run_id))
        if state["provider_attempted"]:
            raise
        return LangSmithTraceResult(generation=provider_call())


def trace_embedding_call(
    *,
    provider: str,
    model: str,
    feature: str,
    prompt_characters: int,
    provider_call: Callable[[], T],
    usage_builder: Callable[[T], Any],
) -> LangSmithEmbeddingTraceResult[T]:
    """Run one embedding request in an optional metadata-only LangSmith span."""

    if not _ready():
        response = provider_call()
        return LangSmithEmbeddingTraceResult(response=response, usage=usage_builder(response))

    try:
        from langsmith import traceable, uuid7
    except Exception:
        response = provider_call()
        return LangSmithEmbeddingTraceResult(response=response, usage=usage_builder(response))

    run_id = uuid7()
    holder: dict[str, Any] = {}
    state = {"provider_attempted": False}

    @traceable(
        name="LifeOS document embedding",
        run_type="embedding",
        metadata={
            "ls_provider": str(provider),
            "ls_model_name": str(model),
            "lifeos_feature": str(feature),
            "prompt_characters": int(prompt_characters),
            "content_logged": False,
            "privacy_mode": "metadata_only",
        },
        tags=["lifeos", str(feature or "document_embedding")],
        process_inputs=lambda _inputs: {"content_logged": False},
        exceptions_to_handle=(Exception,),
    )
    def _traced_call() -> dict[str, Any]:
        state["provider_attempted"] = True
        response = provider_call()
        usage = usage_builder(response)
        holder["response"] = response
        holder["usage"] = usage
        usage_metadata = usage.to_langsmith_usage()
        from services.ai_pricing_service import calculate_usage_cost
        cost = calculate_usage_cost(provider=provider, model=model, usage=usage)
        if cost.input_cost_usd is not None:
            usage_metadata["input_cost"] = float(cost.input_cost_usd)
        if cost.output_cost_usd is not None:
            usage_metadata["output_cost"] = float(cost.output_cost_usd)
        if cost.total_cost_usd is not None:
            usage_metadata["total_cost"] = float(cost.total_cost_usd)
        return {
            "status": "completed",
            "usage_metadata": usage_metadata,
            "content_logged": False,
        }

    try:
        _traced_call(
            langsmith_extra={
                "run_id": run_id,
                "metadata": _base_metadata(feature=feature),
            }
        )
        if "response" not in holder or "usage" not in holder:
            response = provider_call()
            return LangSmithEmbeddingTraceResult(response=response, usage=usage_builder(response))
        return LangSmithEmbeddingTraceResult(
            response=holder["response"],
            usage=holder["usage"],
            run_id=str(run_id),
        )
    except Exception:
        if "response" in holder and "usage" in holder:
            return LangSmithEmbeddingTraceResult(
                response=holder["response"],
                usage=holder["usage"],
                run_id=str(run_id),
            )
        if state["provider_attempted"]:
            raise
        response = provider_call()
        return LangSmithEmbeddingTraceResult(response=response, usage=usage_builder(response))

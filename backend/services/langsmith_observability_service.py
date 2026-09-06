"""Optional privacy-conscious LangSmith tracing for provider calls.

LifeOS cost accounting never depends on LangSmith. Tracing is an observability
copy that can be enabled per environment. By default only metadata, token counts,
and output size are sent; document/user prompt content is not sent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, TypeVar

from ai.providers.base import ProviderGeneration
from services.ai_pricing_service import calculate_usage_cost


T = TypeVar("T", bound=ProviderGeneration)


@dataclass(frozen=True)
class LangSmithTraceResult:
    generation: ProviderGeneration
    run_id: str | None = None


def _enabled() -> bool:
    return (os.getenv("LANGSMITH_TRACING") or "").strip().lower() in {"1", "true", "yes", "on"}


def trace_generation_call(
    *,
    provider: str,
    model: str,
    feature: str,
    prompt_characters: int,
    provider_call: Callable[[], ProviderGeneration],
) -> LangSmithTraceResult:
    """Run one provider call inside an optional LangSmith LLM trace.

    The trace function intentionally accepts no raw prompt argument, so standard
    tracing cannot accidentally capture document contents. A future explicit
    debug mode can add content tracing with a separate privacy review.
    """

    if not _enabled():
        return LangSmithTraceResult(generation=provider_call())

    try:
        from langsmith import traceable, uuid7
    except Exception:
        # Observability must never break the user's AI request.
        return LangSmithTraceResult(generation=provider_call())

    run_id = uuid7()
    holder: dict[str, ProviderGeneration] = {}
    state = {"provider_attempted": False}

    @traceable(
        name="LifeOS AI generation",
        run_type="llm",
        metadata={
            "ls_provider": str(provider),
            "ls_model_name": str(model),
            "lifeos_feature": str(feature),
            "prompt_characters": int(prompt_characters),
            "content_logged": False,
        },
        tags=["lifeos", str(feature or "unknown")],
    )
    def _traced_call() -> dict:
        state["provider_attempted"] = True
        generation = provider_call()
        holder["generation"] = generation
        usage_metadata = generation.usage.to_langsmith_usage()
        cost = calculate_usage_cost(
            provider=provider,
            model=model,
            usage=generation.usage,
        )
        if cost.input_cost_usd is not None:
            usage_metadata["input_cost"] = float(cost.input_cost_usd)
        if cost.output_cost_usd is not None:
            usage_metadata["output_cost"] = float(cost.output_cost_usd)
        return {
            "output_characters": len(generation.text or ""),
            "usage_metadata": usage_metadata,
        }

    try:
        _traced_call(langsmith_extra={"run_id": run_id})
        generation = holder.get("generation")
        if generation is None:
            return LangSmithTraceResult(generation=provider_call())
        return LangSmithTraceResult(generation=generation, run_id=str(run_id))
    except Exception:
        # Never retry a provider call because telemetry failed. Provider errors must
        # propagate to the router exactly once; completed calls can reuse the holder.
        generation = holder.get("generation")
        if generation is not None:
            return LangSmithTraceResult(generation=generation, run_id=str(run_id))
        if state["provider_attempted"]:
            raise
        return LangSmithTraceResult(generation=provider_call())

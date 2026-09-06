"""Deterministic token-cost calculation for LifeOS AI usage.

Prices are configuration, never model reasoning. Built-in values are conservative
snapshots for the models LifeOS currently uses and can be overridden per model in
environment variables without changing application code.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from ai.providers.base import ProviderUsage


@dataclass(frozen=True)
class ModelPricing:
    provider: str
    model: str
    input_per_million_usd: Decimal
    cached_input_per_million_usd: Decimal
    output_per_million_usd: Decimal
    source: str


@dataclass(frozen=True)
class UsageCost:
    input_cost_usd: Decimal | None
    output_cost_usd: Decimal | None
    total_cost_usd: Decimal | None
    pricing_source: str | None


# Snapshot verified against provider pricing on 2026-09-06. Keep overrides in
# deployment config so a pricing change does not require a code release.
_BUILTIN_PRICING: dict[tuple[str, str], tuple[str, str, str]] = {
    ("gemini", "gemini-2.5-flash"): ("0.30", "0.03", "2.50"),
    ("gemini", "gemini-2.5-flash-lite"): ("0.10", "0.01", "0.40"),
    # Embedding text input only; output vectors are not billed as output tokens.
    ("gemini", "gemini-embedding-2"): ("0.20", "0.20", "0.00"),
    ("gemini", "gemini-embedding-001"): ("0.15", "0.15", "0.00"),
}


def _env_model_key(provider: str, model: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", f"{provider}_{model}".upper()).strip("_")
    return f"AI_PRICE_{normalized}"


def _decimal_env(name: str) -> Decimal | None:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    return max(Decimal("0"), value)


def get_model_pricing(provider: str, model: str) -> ModelPricing | None:
    provider_key = str(provider or "").strip().lower()
    model_key = str(model or "").strip().lower()
    prefix = _env_model_key(provider_key, model_key)

    env_input = _decimal_env(f"{prefix}_INPUT_PER_MILLION_USD")
    env_cached = _decimal_env(f"{prefix}_CACHED_INPUT_PER_MILLION_USD")
    env_output = _decimal_env(f"{prefix}_OUTPUT_PER_MILLION_USD")
    if env_input is not None and env_output is not None:
        return ModelPricing(
            provider=provider_key,
            model=model_key,
            input_per_million_usd=env_input,
            cached_input_per_million_usd=env_cached if env_cached is not None else env_input,
            output_per_million_usd=env_output,
            source=f"env:{prefix}",
        )

    builtin = _BUILTIN_PRICING.get((provider_key, model_key))
    if builtin is None:
        return None
    input_rate, cached_rate, output_rate = builtin
    return ModelPricing(
        provider=provider_key,
        model=model_key,
        input_per_million_usd=Decimal(input_rate),
        cached_input_per_million_usd=Decimal(cached_rate),
        output_per_million_usd=Decimal(output_rate),
        source="builtin:2026-09-06",
    )


def calculate_usage_cost(*, provider: str, model: str, usage: ProviderUsage) -> UsageCost:
    pricing = get_model_pricing(provider, model)
    if pricing is None or usage.input_tokens is None:
        return UsageCost(None, None, None, pricing.source if pricing else None)

    million = Decimal("1000000")
    input_tokens = max(0, int(usage.input_tokens or 0))
    cached_tokens = min(input_tokens, max(0, int(usage.cached_input_tokens or 0)))
    uncached_tokens = input_tokens - cached_tokens

    input_cost = (
        Decimal(uncached_tokens) * pricing.input_per_million_usd
        + Decimal(cached_tokens) * pricing.cached_input_per_million_usd
    ) / million

    billable_output = usage.billable_output_tokens
    output_cost = None
    if billable_output is not None:
        output_cost = Decimal(max(0, int(billable_output))) * pricing.output_per_million_usd / million

    total_cost = input_cost + (output_cost or Decimal("0"))
    return UsageCost(
        input_cost_usd=input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=total_cost,
        pricing_source=pricing.source,
    )

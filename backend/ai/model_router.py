"""Deterministic LifeOS model-tier routing.

The model router answers one narrow question: which configured model should handle
this already-classified LifeOS AI feature? It never calls an LLM, never performs
workspace writes, and never changes the feature/service ownership boundary.

Provider routing (Gemini/OpenAI + fallback) remains in ``ai.provider_router``.
This module only selects a model *within* the selected provider so deployment can
map CHEAP/NORMAL/DEEP tiers independently without touching feature code.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Final, Iterator

TIER_CHEAP: Final[str] = "cheap"
TIER_NORMAL: Final[str] = "normal"
TIER_DEEP: Final[str] = "deep"
MODEL_TIERS: Final[tuple[str, str, str]] = (TIER_CHEAP, TIER_NORMAL, TIER_DEEP)

_MODEL_TIER_ALIASES: Final[dict[str, str]] = {
    "cheap": TIER_CHEAP,
    "fast": TIER_CHEAP,
    "normal": TIER_NORMAL,
    "balanced": TIER_NORMAL,
    "deep": TIER_DEEP,
}

# User-selected Ask LifeOS tiers apply only to the primary reasoning/answer
# generation. Trust/safety helper calls such as answerability and claim
# verification retain their deterministic feature tier so a Fast answer never
# weakens the verification boundary.
_USER_SELECTABLE_EXACT: Final[frozenset[str]] = frozenset({
    "ask_lifeos_reasoner",
    "ask_lifeos_advisor",
    "ask_lifeos_general_reasoner",
    "agent_reasoning",
})
_USER_SELECTABLE_PREFIXES: Final[tuple[str, ...]] = (
    "ai_service.ask_",
)

_MODEL_TIER_OVERRIDE: ContextVar[str | None] = ContextVar(
    "lifeos_model_tier_override", default=None
)

# Keep this registry intentionally small and deterministic. Features not listed
# here default to NORMAL so new functionality never silently drops to a weaker
# model merely because the router does not know it yet.
_FEATURE_TIER_EXACT: Final[dict[str, str]] = {
    # Narrow classification/gating work. These are the first candidates for a
    # cheaper model once GEMINI_CHEAP_MODEL / OPENAI_CHEAP_MODEL is configured.
    "document_type_detection": TIER_CHEAP,
    "document_answerability": TIER_CHEAP,
    # Trust-sensitive or synthesis work stays NORMAL by default.
    "document_comparison_verifier": TIER_NORMAL,
    "ask_lifeos_claim_verifier": TIER_NORMAL,
    "ask_lifeos_reasoner": TIER_NORMAL,
    "ask_lifeos_advisor": TIER_NORMAL,
    "ask_lifeos_general_reasoner": TIER_NORMAL,
    "ask_lifeos_general_verifier": TIER_NORMAL,
    "ask_lifeos_request_understanding": TIER_CHEAP,
    "ask_lifeos_web_research": TIER_CHEAP,
    "academic_schedule_extraction": TIER_NORMAL,
    # Complex I19 goal reasoning gets the DEEP tier. Today DEEP can still map to
    # the same Gemini model; later deployment can point it at GPT-5 or equivalent.
    "agent_reasoning": TIER_DEEP,
}

_FEATURE_TIER_PREFIXES: Final[tuple[tuple[str, str], ...]] = (
    ("ai_service.", TIER_NORMAL),
)


@dataclass(frozen=True)
class ModelRoute:
    feature: str
    tier: str
    provider: str
    requested_model: str
    selected_model: str
    enabled: bool
    source: str
    tier_source: str = "feature_default"

    @property
    def changed(self) -> bool:
        return self.selected_model != self.requested_model


def _bool_env(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _safe_feature(feature: str | None) -> str:
    return str(feature or "unknown").strip().lower().replace(" ", "_")[:80] or "unknown"




def normalize_model_tier(value: str | None, *, allow_none: bool = True) -> str | None:
    """Normalize a user/API tier value without making any provider call."""

    if value is None or not str(value).strip():
        if allow_none:
            return None
        raise ValueError("Choose Fast, Balanced, or Deep.")
    normalized = _MODEL_TIER_ALIASES.get(str(value).strip().lower())
    if normalized is None:
        raise ValueError("Choose Fast, Balanced, or Deep.")
    return normalized


def current_model_tier_override() -> str | None:
    return _MODEL_TIER_OVERRIDE.get()


@contextmanager
def model_tier_override(value: str | None) -> Iterator[str | None]:
    """Scope a user-selected Ask LifeOS model tier to one request/operation."""

    normalized = normalize_model_tier(value, allow_none=True)
    token = _MODEL_TIER_OVERRIDE.set(normalized)
    try:
        yield normalized
    finally:
        _MODEL_TIER_OVERRIDE.reset(token)


def _user_override_allowed(feature: str) -> bool:
    if feature in _USER_SELECTABLE_EXACT:
        return True
    return any(feature.startswith(prefix) for prefix in _USER_SELECTABLE_PREFIXES)


def tier_for_feature(feature: str | None) -> str:
    safe = _safe_feature(feature)
    exact = _FEATURE_TIER_EXACT.get(safe)
    if exact:
        return exact
    for prefix, tier in _FEATURE_TIER_PREFIXES:
        if safe.startswith(prefix):
            return tier
    return TIER_NORMAL


def _provider_prefix(provider: str) -> str:
    return str(provider or "").strip().upper().replace("-", "_")


def _tier_env_name(provider: str, tier: str) -> str:
    return f"{_provider_prefix(provider)}_{tier.upper()}_MODEL"


def _configured_tier_model(*, provider: str, tier: str, requested_model: str) -> tuple[str, str]:
    env_name = _tier_env_name(provider, tier)
    configured = (os.getenv(env_name) or "").strip()
    if configured:
        return configured, f"env:{env_name}"
    # Safe initial rollout: every tier inherits the model the feature already
    # requested until a tier-specific model is explicitly configured.
    return requested_model, "requested_model"


def resolve_model_route(*, feature: str, provider: str, requested_model: str) -> ModelRoute:
    safe_feature = _safe_feature(feature)
    safe_provider = str(provider or "").strip().lower()
    safe_model = str(requested_model or "").strip()
    feature_tier = tier_for_feature(safe_feature)
    enabled = _bool_env("AI_MODEL_ROUTER_ENABLED", True)
    request_override = current_model_tier_override()
    override_applies = bool(
        enabled and request_override and _user_override_allowed(safe_feature)
    )
    tier = request_override if override_applies else feature_tier
    tier_source = "user_override" if override_applies else "feature_default"

    if not enabled or not safe_provider or not safe_model:
        return ModelRoute(
            feature=safe_feature,
            tier=tier,
            provider=safe_provider,
            requested_model=safe_model,
            selected_model=safe_model,
            enabled=enabled,
            source="disabled" if not enabled else "requested_model",
            tier_source=tier_source,
        )

    selected_model, source = _configured_tier_model(
        provider=safe_provider,
        tier=tier,
        requested_model=safe_model,
    )
    return ModelRoute(
        feature=safe_feature,
        tier=tier,
        provider=safe_provider,
        requested_model=safe_model,
        selected_model=selected_model,
        enabled=True,
        source=source,
        tier_source=tier_source,
    )


def _active_provider_and_model() -> tuple[str, str]:
    provider = (os.getenv("AI_PROVIDER") or "gemini").strip().lower()
    if provider == "gemini":
        model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    elif provider == "openai":
        model = (os.getenv("OPENAI_MODEL") or "").strip()
    else:
        model = ""
    return provider, model


def model_router_status() -> dict:
    """Return secret-free development diagnostics for Analytics -> AI Usage."""

    provider, base_model = _active_provider_and_model()
    enabled = _bool_env("AI_MODEL_ROUTER_ENABLED", True)
    tiers = []
    for tier in MODEL_TIERS:
        selected, source = _configured_tier_model(
            provider=provider,
            tier=tier,
            requested_model=base_model,
        )
        if not enabled:
            selected, source = base_model, "disabled"
        tiers.append(
            {
                "tier": tier,
                "model": selected,
                "source": source,
            }
        )

    return {
        "enabled": enabled,
        "provider": provider,
        "base_model": base_model,
        "tiers": tiers,
        "feature_routes": [
            {"feature": feature, "tier": tier}
            for feature, tier in sorted(_FEATURE_TIER_EXACT.items())
        ],
        "default_tier": TIER_NORMAL,
    }

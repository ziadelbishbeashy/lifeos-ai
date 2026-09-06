"""Route LifeOS generation requests to configured AI providers.

Feature services remain provider-independent. The router owns adapter selection,
optional fallback behaviour, consistent provider errors, exact token metering,
cost calculation, and optional LangSmith observability.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable

from ai.providers import GeminiProvider, OpenAIProvider, ProviderRequestError
from ai.providers.base import ProviderGeneration, ProviderUsage
from services.ai_pricing_service import UsageCost, calculate_usage_cost
from services.ai_usage_service import record_generation_usage
from services.langsmith_observability_service import trace_generation_call
from services.resource_limit_service import ResourceLimitError, guard_generation_request


class AIProviderRouterError(RuntimeError):
    """Friendly provider error consumed by the LifeOS service layer."""


class AIProviderBudgetError(AIProviderRouterError):
    """Raised when Step 20 blocks an oversized or over-budget provider call."""


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    api_key: str
    model: str


_PROVIDER_FACTORIES: dict[str, Callable[[str], object]] = {
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
}


def _provider_config(name: str) -> ProviderConfig | None:
    provider = (name or "").strip().lower()
    if provider == "gemini":
        key = (os.getenv("GEMINI_API_KEY") or "").strip()
        model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    elif provider == "openai":
        key = (os.getenv("OPENAI_API_KEY") or "").strip()
        model = (os.getenv("OPENAI_MODEL") or "").strip()
    else:
        return None

    if not key or not model:
        return None
    return ProviderConfig(name=provider, api_key=key, model=model)


def active_provider_config() -> ProviderConfig:
    provider = (os.getenv("AI_PROVIDER") or "gemini").strip().lower()
    if provider not in _PROVIDER_FACTORIES:
        raise AIProviderRouterError(
            f'Unsupported AI provider: "{provider}". Use "gemini" or "openai".'
        )

    config = _provider_config(provider)
    if config is None:
        key_name = "GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY"
        model_name = "GEMINI_MODEL" if provider == "gemini" else "OPENAI_MODEL"
        raise AIProviderRouterError(
            f"Configure {key_name} and {model_name} before using {provider}."
        )
    return config


def fallback_provider_config(primary_name: str) -> ProviderConfig | None:
    fallback_name = (os.getenv("AI_FALLBACK_PROVIDER") or "").strip().lower()
    if not fallback_name or fallback_name == primary_name:
        return None
    if fallback_name not in _PROVIDER_FACTORIES:
        return None
    return _provider_config(fallback_name)


def friendly_provider_error(provider: str, error: Exception) -> str:
    message = str(error)
    normalized = message.lower()

    if "503" in message or "unavailable" in normalized:
        return (
            f"{provider.title()} is temporarily experiencing high demand. "
            "Please try again shortly."
        )
    if "429" in message or "resource_exhausted" in normalized:
        return (
            f"{provider.title()} usage limit was reached. "
            "Please wait before trying again."
        )
    if (
        "401" in message
        or "403" in message
        or "api key" in normalized
        or "authentication" in normalized
    ):
        return (
            f"{provider.title()} authentication failed. "
            "Check the API key in your .env file."
        )
    if "model" in normalized and (
        "not found" in normalized or "invalid" in normalized
    ):
        return (
            f"The configured {provider.title()} model is unavailable. "
            "Check the model name in your .env file."
        )
    return (
        f"{provider.title()} could not complete the request. "
        "Please try again shortly."
    )


def _normalize_generation(value) -> ProviderGeneration:
    if isinstance(value, ProviderGeneration):
        return value
    return ProviderGeneration(text=str(value or "").strip(), usage=ProviderUsage())


def _record_attempt(
    *,
    config: ProviderConfig,
    feature: str,
    prompt: str,
    call_index: int,
    usage: ProviderUsage,
    latency_ms: int,
    success: bool,
    error_category: str | None = None,
    langsmith_run_id: str | None = None,
) -> None:
    cost = calculate_usage_cost(provider=config.name, model=config.model, usage=usage)
    record_generation_usage(
        provider=config.name,
        model=config.model,
        feature=feature,
        prompt_characters=len(str(prompt or "")),
        provider_call_index=call_index,
        usage=usage,
        cost=cost,
        latency_ms=latency_ms,
        success=success,
        error_category=error_category,
        langsmith_run_id=langsmith_run_id,
    )


def _execute(config: ProviderConfig, prompt: str, *, feature: str) -> str:
    try:
        call_index = guard_generation_request(
            provider=config.name,
            model=config.model,
            prompt=prompt,
        )
    except ResourceLimitError as error:
        raise AIProviderBudgetError(str(error)) from error

    factory = _PROVIDER_FACTORIES[config.name]
    provider = factory(config.api_key)
    started = time.perf_counter()
    try:
        traced = trace_generation_call(
            provider=config.name,
            model=config.model,
            feature=feature,
            prompt_characters=len(str(prompt or "")),
            provider_call=lambda: _normalize_generation(
                provider.generate_text(model=config.model, prompt=prompt)
            ),
        )
        generation = traced.generation
    except ProviderRequestError as error:
        latency_ms = round((time.perf_counter() - started) * 1000)
        _record_attempt(
            config=config,
            feature=feature,
            prompt=prompt,
            call_index=call_index,
            usage=ProviderUsage(),
            latency_ms=latency_ms,
            success=False,
            error_category=type(error).__name__,
        )
        raise AIProviderRouterError(
            friendly_provider_error(config.name, error)
        ) from error
    except Exception as error:
        # LangSmith may wrap/re-raise provider exceptions. Preserve the same
        # friendly product boundary and record the attempted external work once.
        latency_ms = round((time.perf_counter() - started) * 1000)
        _record_attempt(
            config=config,
            feature=feature,
            prompt=prompt,
            call_index=call_index,
            usage=ProviderUsage(),
            latency_ms=latency_ms,
            success=False,
            error_category=type(error).__name__,
        )
        raise AIProviderRouterError(
            friendly_provider_error(config.name, error)
        ) from error

    latency_ms = round((time.perf_counter() - started) * 1000)
    _record_attempt(
        config=config,
        feature=feature,
        prompt=prompt,
        call_index=call_index,
        usage=generation.usage,
        latency_ms=latency_ms,
        success=True,
        langsmith_run_id=traced.run_id,
    )
    return generation.text


def generate_text(
    *,
    provider: str,
    api_key: str,
    model: str,
    prompt: str,
    empty_message: str,
    feature: str = "unknown",
) -> str:
    """Generate through the requested provider and optional configured fallback.

    ``feature`` is observability metadata only. It never changes model behavior.
    The API key is never logged or included in errors.
    """

    primary = ProviderConfig(
        name=(provider or "").strip().lower(),
        api_key=api_key,
        model=model,
    )
    if primary.name not in _PROVIDER_FACTORIES:
        raise AIProviderRouterError(
            f'Unsupported AI provider: "{primary.name}".'
        )

    safe_feature = str(feature or "unknown").strip().lower().replace(" ", "_")[:80] or "unknown"
    try:
        result = _execute(primary, prompt, feature=safe_feature)
        if not result:
            raise AIProviderRouterError(empty_message)
        return result
    except AIProviderBudgetError:
        # A LifeOS budget/size boundary is intentional. Do not spend another
        # provider call trying a fallback after Step 20 has rejected the request.
        raise
    except AIProviderRouterError as primary_error:
        fallback = fallback_provider_config(primary.name)
        if fallback is None:
            raise
        try:
            result = _execute(fallback, prompt, feature=safe_feature)
            if not result:
                raise AIProviderRouterError(empty_message)
            return result
        except AIProviderRouterError as fallback_error:
            raise AIProviderRouterError(
                f"Primary provider failed: {primary_error} "
                f"Fallback provider failed: {fallback_error}"
            ) from fallback_error

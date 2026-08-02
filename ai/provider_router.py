"""Route LifeOS generation requests to configured AI providers.

Feature services remain provider-independent. The router owns adapter selection,
optional fallback behaviour, and consistent user-facing provider errors.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from ai.providers import GeminiProvider, OpenAIProvider, ProviderRequestError


class AIProviderRouterError(RuntimeError):
    """Friendly provider error consumed by the LifeOS service layer."""


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


def _execute(config: ProviderConfig, prompt: str) -> str:
    factory = _PROVIDER_FACTORIES[config.name]
    provider = factory(config.api_key)
    try:
        return provider.generate_text(model=config.model, prompt=prompt)
    except ProviderRequestError as error:
        raise AIProviderRouterError(
            friendly_provider_error(config.name, error)
        ) from error


def generate_text(
    *,
    provider: str,
    api_key: str,
    model: str,
    prompt: str,
    empty_message: str,
) -> str:
    """Generate through the requested provider and optional configured fallback.

    The explicit arguments preserve compatibility with the existing ai_service
    public API. The API key is never logged or included in errors.
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

    try:
        result = _execute(primary, prompt)
        if not result:
            raise AIProviderRouterError(empty_message)
        return result
    except AIProviderRouterError as primary_error:
        fallback = fallback_provider_config(primary.name)
        if fallback is None:
            raise
        try:
            result = _execute(fallback, prompt)
            if not result:
                raise AIProviderRouterError(empty_message)
            return result
        except AIProviderRouterError as fallback_error:
            raise AIProviderRouterError(
                f"Primary provider failed: {primary_error} "
                f"Fallback provider failed: {fallback_error}"
            ) from fallback_error

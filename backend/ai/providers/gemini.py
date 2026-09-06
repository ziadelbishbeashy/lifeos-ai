"""Gemini provider adapter with lazy SDK imports and exact usage capture."""

from __future__ import annotations

from typing import Any

from ai.providers.base import (
    AIProvider,
    ProviderGeneration,
    ProviderRequestError,
    ProviderUsage,
)


def _usage_value(usage: Any, *names: str) -> int | None:
    for name in names:
        value = getattr(usage, name, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(name)
        if value is None:
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return None


def _extract_usage(response: Any) -> ProviderUsage:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return ProviderUsage()

    input_tokens = _usage_value(usage, "prompt_token_count", "promptTokenCount")
    output_tokens = _usage_value(usage, "candidates_token_count", "candidatesTokenCount")
    thinking_tokens = _usage_value(usage, "thoughts_token_count", "thoughtsTokenCount")
    cached_tokens = _usage_value(
        usage,
        "cached_content_token_count",
        "cachedContentTokenCount",
    )
    total_tokens = _usage_value(usage, "total_token_count", "totalTokenCount")

    raw = {
        "prompt_token_count": input_tokens,
        "candidates_token_count": output_tokens,
        "thoughts_token_count": thinking_tokens,
        "cached_content_token_count": cached_tokens,
        "total_token_count": total_tokens,
    }
    return ProviderUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        cached_input_tokens=cached_tokens,
        total_tokens=total_tokens,
        raw=raw,
    )


class GeminiProvider(AIProvider):
    provider_name = "gemini"

    def generate_text(self, *, model: str, prompt: str) -> ProviderGeneration:
        try:
            from google import genai

            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )
            return ProviderGeneration(
                text=(response.text or "").strip(),
                usage=_extract_usage(response),
            )
        except Exception as error:
            raise ProviderRequestError(str(error)) from error

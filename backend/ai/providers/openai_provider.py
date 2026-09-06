"""OpenAI provider adapter with lazy SDK imports and usage capture when available."""

from __future__ import annotations

from typing import Any

from ai.providers.base import (
    AIProvider,
    ProviderGeneration,
    ProviderRequestError,
    ProviderUsage,
)


def _value(obj: Any, *names: str) -> int | None:
    for name in names:
        value = getattr(obj, name, None)
        if value is None and isinstance(obj, dict):
            value = obj.get(name)
        if value is None:
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return None


class OpenAIProvider(AIProvider):
    provider_name = "openai"

    def generate_text(self, *, model: str, prompt: str) -> ProviderGeneration:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            response = client.responses.create(model=model, input=prompt)
            usage = getattr(response, "usage", None)
            input_tokens = _value(usage, "input_tokens") if usage is not None else None
            output_tokens = _value(usage, "output_tokens") if usage is not None else None
            total_tokens = _value(usage, "total_tokens") if usage is not None else None

            cached_tokens = None
            input_details = getattr(usage, "input_tokens_details", None) if usage is not None else None
            if input_details is not None:
                cached_tokens = _value(input_details, "cached_tokens")

            reasoning_tokens = None
            output_details = getattr(usage, "output_tokens_details", None) if usage is not None else None
            if output_details is not None:
                reasoning_tokens = _value(output_details, "reasoning_tokens")

            # Responses API output_tokens includes reasoning tokens. LifeOS stores
            # visible/non-reasoning output separately so billable output can be
            # calculated consistently across providers without double counting.
            visible_output_tokens = output_tokens
            if output_tokens is not None and reasoning_tokens is not None:
                visible_output_tokens = max(0, output_tokens - reasoning_tokens)

            return ProviderGeneration(
                text=(response.output_text or "").strip(),
                usage=ProviderUsage(
                    input_tokens=input_tokens,
                    output_tokens=visible_output_tokens,
                    thinking_tokens=reasoning_tokens,
                    cached_input_tokens=cached_tokens,
                    total_tokens=total_tokens,
                ),
            )
        except Exception as error:
            raise ProviderRequestError(str(error)) from error

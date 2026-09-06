"""Base contracts shared by all LifeOS AI providers.

Provider adapters return text plus usage metadata when the upstream SDK exposes it.
The router still accepts legacy string-returning adapters so existing tests and
future provider integrations can migrate incrementally.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class ProviderRequestError(RuntimeError):
    """Provider-level error before it is converted to a product message."""


@dataclass(frozen=True)
class ProviderUsage:
    """Provider-reported token accounting for one generation call.

    All values are raw provider counts. ``output_tokens`` means visible candidate
    tokens; ``thinking_tokens`` is tracked separately because reasoning models
    can bill it as output even when it is not visible to the user.
    """

    input_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None
    cached_input_tokens: int | None = None
    total_tokens: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def billable_output_tokens(self) -> int | None:
        values = [self.output_tokens, self.thinking_tokens]
        if all(value is None for value in values):
            return None
        return sum(max(0, int(value or 0)) for value in values)

    def to_langsmith_usage(self) -> dict[str, Any]:
        """Return the usage shape LangSmith understands for custom LLM traces."""

        result: dict[str, Any] = {}
        if self.input_tokens is not None:
            result["input_tokens"] = int(self.input_tokens)
        billable_output = self.billable_output_tokens
        if billable_output is not None:
            result["output_tokens"] = int(billable_output)
        if self.total_tokens is not None:
            result["total_tokens"] = int(self.total_tokens)
        if self.cached_input_tokens:
            result["input_token_details"] = {
                "cache_read": int(self.cached_input_tokens),
            }
        if self.thinking_tokens:
            result["output_token_details"] = {
                "reasoning": int(self.thinking_tokens),
            }
        return result


@dataclass(frozen=True)
class ProviderGeneration:
    """One provider generation result without exposing provider SDK objects."""

    text: str
    usage: ProviderUsage = field(default_factory=ProviderUsage)


class AIProvider(ABC):
    """Small provider contract used by the LifeOS AI router."""

    provider_name: str

    def __init__(self, api_key: str):
        self.api_key = api_key

    @abstractmethod
    def generate_text(self, *, model: str, prompt: str) -> str | ProviderGeneration:
        """Return generated text/usage or raise ProviderRequestError."""

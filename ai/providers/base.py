"""Base contracts shared by all LifeOS AI providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ProviderRequestError(RuntimeError):
    """Provider-level error before it is converted to a product message."""


class AIProvider(ABC):
    """Small provider contract used by the LifeOS AI router."""

    provider_name: str

    def __init__(self, api_key: str):
        self.api_key = api_key

    @abstractmethod
    def generate_text(self, *, model: str, prompt: str) -> str:
        """Return generated text or raise ProviderRequestError."""

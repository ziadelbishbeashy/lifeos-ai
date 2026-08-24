"""Provider router behaviour without external API calls."""

import pytest

from ai import provider_router
from ai.provider_router import AIProviderRouterError


class FakeProvider:
    def __init__(self, api_key):
        self.api_key = api_key

    def generate_text(self, *, model, prompt):
        return f"{model}:{prompt}"


class FailingProvider(FakeProvider):
    def generate_text(self, *, model, prompt):
        from ai.providers.base import ProviderRequestError

        raise ProviderRequestError("503 unavailable")


def test_router_generates_with_selected_provider(monkeypatch):
    monkeypatch.setitem(provider_router._PROVIDER_FACTORIES, "fake", FakeProvider)
    result = provider_router.generate_text(
        provider="fake",
        api_key="secret",
        model="model-1",
        prompt="hello",
        empty_message="empty",
    )
    assert result == "model-1:hello"


def test_router_returns_friendly_error(monkeypatch):
    monkeypatch.setitem(
        provider_router._PROVIDER_FACTORIES,
        "fake-fail",
        FailingProvider,
    )
    with pytest.raises(AIProviderRouterError) as captured:
        provider_router.generate_text(
            provider="fake-fail",
            api_key="secret",
            model="model-1",
            prompt="hello",
            empty_message="empty",
        )
    assert "temporarily experiencing high demand" in str(captured.value)

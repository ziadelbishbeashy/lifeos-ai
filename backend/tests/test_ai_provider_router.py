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


def test_router_applies_feature_tier_model_override(monkeypatch):
    monkeypatch.setitem(provider_router._PROVIDER_FACTORIES, "gemini", FakeProvider)
    monkeypatch.setenv("AI_MODEL_ROUTER_ENABLED", "true")
    monkeypatch.setenv("GEMINI_CHEAP_MODEL", "gemini-2.5-flash-lite")
    result = provider_router.generate_text(
        provider="gemini",
        api_key="secret",
        model="gemini-2.5-flash",
        prompt="classify",
        empty_message="empty",
        feature="document_type_detection",
    )
    assert result == "gemini-2.5-flash-lite:classify"


def test_router_keeps_normal_feature_on_requested_model_without_override(monkeypatch):
    monkeypatch.setitem(provider_router._PROVIDER_FACTORIES, "gemini", FakeProvider)
    monkeypatch.setenv("AI_MODEL_ROUTER_ENABLED", "true")
    monkeypatch.delenv("GEMINI_NORMAL_MODEL", raising=False)
    result = provider_router.generate_text(
        provider="gemini",
        api_key="secret",
        model="gemini-2.5-flash",
        prompt="analyze",
        empty_message="empty",
        feature="ai_service.analyze_document",
    )
    assert result == "gemini-2.5-flash:analyze"

def test_router_json_mode_uses_provider_native_json_generation(monkeypatch):
    class JsonProvider(FakeProvider):
        def generate_json_text(self, *, model, prompt):
            return '{"mode":"json","model":"%s"}' % model

    monkeypatch.setitem(provider_router._PROVIDER_FACTORIES, "gemini", JsonProvider)
    monkeypatch.setenv("AI_MODEL_ROUTER_ENABLED", "true")
    monkeypatch.delenv("GEMINI_NORMAL_MODEL", raising=False)

    result = provider_router.generate_text(
        provider="gemini",
        api_key="secret",
        model="gemini-2.5-flash",
        prompt="Return JSON",
        empty_message="empty",
        feature="ask_lifeos_general_reasoner",
        json_mode=True,
    )

    assert result == '{"mode":"json","model":"gemini-2.5-flash"}'


def test_router_json_mode_falls_back_to_legacy_provider_method(monkeypatch):
    monkeypatch.setitem(provider_router._PROVIDER_FACTORIES, "fake", FakeProvider)
    result = provider_router.generate_text(
        provider="fake",
        api_key="secret",
        model="model-1",
        prompt="hello",
        empty_message="empty",
        json_mode=True,
    )
    assert result == "model-1:hello"


"""Deterministic model-tier routing without external provider calls."""

from ai.model_router import (
    TIER_CHEAP,
    TIER_DEEP,
    TIER_NORMAL,
    model_router_status,
    resolve_model_route,
    tier_for_feature,
)


def test_feature_tiers_are_deterministic():
    assert tier_for_feature("document_type_detection") == TIER_CHEAP
    assert tier_for_feature("document_answerability") == TIER_CHEAP
    assert tier_for_feature("agent_reasoning") == TIER_DEEP
    assert tier_for_feature("ask_lifeos_reasoner") == TIER_NORMAL
    assert tier_for_feature("ask_lifeos_advisor") == TIER_NORMAL
    assert tier_for_feature("ai_service.analyze_document") == TIER_NORMAL
    assert tier_for_feature("brand_new_feature") == TIER_NORMAL


def test_router_inherits_existing_model_without_tier_override(monkeypatch):
    monkeypatch.setenv("AI_MODEL_ROUTER_ENABLED", "true")
    monkeypatch.delenv("GEMINI_CHEAP_MODEL", raising=False)
    route = resolve_model_route(
        feature="document_type_detection",
        provider="gemini",
        requested_model="gemini-2.5-flash",
    )
    assert route.tier == TIER_CHEAP
    assert route.selected_model == "gemini-2.5-flash"
    assert route.changed is False
    assert route.source == "requested_model"


def test_router_uses_provider_specific_tier_override(monkeypatch):
    monkeypatch.setenv("AI_MODEL_ROUTER_ENABLED", "true")
    monkeypatch.setenv("GEMINI_CHEAP_MODEL", "gemini-2.5-flash-lite")
    route = resolve_model_route(
        feature="document_type_detection",
        provider="gemini",
        requested_model="gemini-2.5-flash",
    )
    assert route.tier == TIER_CHEAP
    assert route.selected_model == "gemini-2.5-flash-lite"
    assert route.changed is True
    assert route.source == "env:GEMINI_CHEAP_MODEL"


def test_router_can_be_disabled_as_a_safe_rollback(monkeypatch):
    monkeypatch.setenv("AI_MODEL_ROUTER_ENABLED", "false")
    monkeypatch.setenv("GEMINI_CHEAP_MODEL", "gemini-2.5-flash-lite")
    route = resolve_model_route(
        feature="document_type_detection",
        provider="gemini",
        requested_model="gemini-2.5-flash",
    )
    assert route.enabled is False
    assert route.selected_model == "gemini-2.5-flash"
    assert route.source == "disabled"


def test_deep_tier_can_be_configured_independently(monkeypatch):
    monkeypatch.setenv("AI_MODEL_ROUTER_ENABLED", "true")
    monkeypatch.setenv("GEMINI_DEEP_MODEL", "gemini-deep-test")
    route = resolve_model_route(
        feature="agent_reasoning",
        provider="gemini",
        requested_model="gemini-2.5-flash",
    )
    assert route.tier == TIER_DEEP
    assert route.selected_model == "gemini-deep-test"


def test_status_is_secret_free_and_reports_tiers(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_CHEAP_MODEL", "gemini-2.5-flash-lite")
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-appear")
    status = model_router_status()
    assert status["provider"] == "gemini"
    assert {entry["tier"] for entry in status["tiers"]} == {"cheap", "normal", "deep"}
    assert status["tiers"][0]["model"] == "gemini-2.5-flash-lite"
    assert "must-not-appear" not in str(status)


def test_ask_user_override_changes_primary_reasoning_only(monkeypatch):
    from ai.model_router import model_tier_override

    monkeypatch.setenv("AI_MODEL_ROUTER_ENABLED", "true")
    monkeypatch.setenv("GEMINI_CHEAP_MODEL", "gemini-fast-test")
    monkeypatch.setenv("GEMINI_NORMAL_MODEL", "gemini-balanced-test")

    with model_tier_override("fast"):
        reasoning = resolve_model_route(
            feature="ask_lifeos_reasoner",
            provider="gemini",
            requested_model="gemini-2.5-flash",
        )
        verifier = resolve_model_route(
            feature="ask_lifeos_claim_verifier",
            provider="gemini",
            requested_model="gemini-2.5-flash",
        )
        answerability = resolve_model_route(
            feature="document_answerability",
            provider="gemini",
            requested_model="gemini-2.5-flash",
        )

    assert reasoning.tier == TIER_CHEAP
    assert reasoning.tier_source == "user_override"
    assert reasoning.selected_model == "gemini-fast-test"
    assert verifier.tier == TIER_NORMAL
    assert verifier.tier_source == "feature_default"
    assert verifier.selected_model == "gemini-balanced-test"
    assert answerability.tier == TIER_CHEAP
    assert answerability.tier_source == "feature_default"


def test_ask_user_override_is_scoped_and_accepts_friendly_aliases(monkeypatch):
    from ai.model_router import current_model_tier_override, model_tier_override

    monkeypatch.setenv("AI_MODEL_ROUTER_ENABLED", "true")
    assert current_model_tier_override() is None
    with model_tier_override("balanced"):
        assert current_model_tier_override() == TIER_NORMAL
        route = resolve_model_route(
            feature="agent_reasoning",
            provider="gemini",
            requested_model="gemini-2.5-flash",
        )
        assert route.tier == TIER_NORMAL
        assert route.tier_source == "user_override"
    assert current_model_tier_override() is None


def test_ask_user_override_applies_to_grounded_answer_generation(monkeypatch):
    from ai.model_router import model_tier_override

    monkeypatch.setenv("AI_MODEL_ROUTER_ENABLED", "true")
    monkeypatch.setenv("GEMINI_DEEP_MODEL", "gemini-deep-test")
    with model_tier_override("deep"):
        route = resolve_model_route(
            feature="ai_service.ask_document_scope_question",
            provider="gemini",
            requested_model="gemini-2.5-flash",
        )
    assert route.tier == TIER_DEEP
    assert route.selected_model == "gemini-deep-test"
    assert route.tier_source == "user_override"

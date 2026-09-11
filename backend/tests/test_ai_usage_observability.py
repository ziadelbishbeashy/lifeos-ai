from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from ai import provider_router
from ai.providers.base import ProviderGeneration, ProviderUsage
from ai.providers.gemini import _extract_usage
from database import db
from models import AIUsageEvent
from services.ai_pricing_service import calculate_usage_cost


def _login(client):
    return client.post(
        "/login",
        data={"email": "student@example.com", "password": "StrongPass123!"},
        follow_redirects=False,
    )


def test_gemini_usage_metadata_is_preserved_exactly():
    response = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=10_000,
            candidates_token_count=1_200,
            thoughts_token_count=800,
            cached_content_token_count=2_000,
            total_token_count=12_000,
        )
    )
    usage = _extract_usage(response)
    assert usage.input_tokens == 10_000
    assert usage.output_tokens == 1_200
    assert usage.thinking_tokens == 800
    assert usage.cached_input_tokens == 2_000
    assert usage.total_tokens == 12_000
    assert usage.billable_output_tokens == 2_000


def test_gemini_flash_cost_uses_uncached_cached_and_reasoning_tokens(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("AI_PRICE_GEMINI_GEMINI_2_5_FLASH_"):
            monkeypatch.delenv(key, raising=False)

    usage = ProviderUsage(
        input_tokens=10_000,
        output_tokens=1_200,
        thinking_tokens=800,
        cached_input_tokens=2_000,
        total_tokens=12_000,
    )
    cost = calculate_usage_cost(
        provider="gemini",
        model="gemini-2.5-flash",
        usage=usage,
    )
    # 8k normal input @ $0.30/M + 2k cached @ $0.03/M = $0.00246
    assert cost.input_cost_usd == Decimal("0.00246")
    # 2k candidate+thinking output @ $2.50/M = $0.005
    assert cost.output_cost_usd == Decimal("0.00500")
    assert cost.total_cost_usd == Decimal("0.00746")


def test_gemini_embedding_cost_uses_exact_input_tokens(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("AI_PRICE_GEMINI_GEMINI_EMBEDDING_2_"):
            monkeypatch.delenv(key, raising=False)

    usage = ProviderUsage(input_tokens=5_000, total_tokens=5_000)
    cost = calculate_usage_cost(
        provider="gemini",
        model="gemini-embedding-2",
        usage=usage,
    )
    assert cost.input_cost_usd == Decimal("0.00100")
    assert cost.output_cost_usd is None
    assert cost.total_cost_usd == Decimal("0.00100")


def test_router_records_feature_usage_without_changing_text_contract(monkeypatch):
    captured = []

    class FakeProvider:
        def __init__(self, api_key):
            self.api_key = api_key

        def generate_text(self, *, model, prompt):
            return ProviderGeneration(
                text="metered answer",
                usage=ProviderUsage(
                    input_tokens=100,
                    output_tokens=20,
                    thinking_tokens=5,
                    cached_input_tokens=10,
                    total_tokens=125,
                ),
            )

    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setitem(provider_router._PROVIDER_FACTORIES, "gemini", FakeProvider)
    monkeypatch.setattr(provider_router, "record_generation_usage", lambda **kwargs: captured.append(kwargs))

    result = provider_router.generate_text(
        provider="gemini",
        api_key="test-key",
        model="gemini-2.5-flash",
        prompt="hello",
        empty_message="empty",
        feature="document_analysis",
    )

    assert result == "metered answer"
    assert len(captured) == 1
    assert captured[0]["feature"] == "document_analysis"
    assert captured[0]["usage"].thinking_tokens == 5
    assert captured[0]["cost"].total_cost_usd is not None
    assert captured[0]["success"] is True


def test_user_can_read_only_owned_ai_usage_summary(client, app, user):
    with app.app_context():
        event = AIUsageEvent(
            user_id=user,
            request_id="req-test",
            endpoint="api_v1_intelligence.ask",
            feature="ask_lifeos_reasoner",
            operation="generation",
            provider="gemini",
            model="gemini-2.5-flash",
            provider_call_index=1,
            prompt_characters=4000,
            input_tokens=1000,
            output_tokens=100,
            thinking_tokens=50,
            cached_input_tokens=200,
            total_tokens=1150,
            input_cost_usd=Decimal("0.000246"),
            output_cost_usd=Decimal("0.000375"),
            total_cost_usd=Decimal("0.000621"),
            pricing_source="test",
            latency_ms=250,
            success=True,
            usage_json="{}",
        )
        db.session.add(event)
        db.session.commit()

    _login(client)
    response = client.get("/api/v1/ai-usage/summary?days=30")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["totals"]["calls"] == 1
    assert payload["totals"]["total_tokens"] == 1150
    assert payload["totals"]["thinking_tokens"] == 50
    assert payload["totals"]["cached_input_tokens"] == 200
    assert payload["totals"]["known_cost_usd"] == 0.000621
    assert payload["by_feature"][0]["feature"] == "ask_lifeos_reasoner"


def test_usage_summary_groups_provider_calls_into_user_operations(client, app, user):
    with app.app_context():
        rows = [
            AIUsageEvent(
                user_id=user,
                request_id="req-analysis",
                endpoint="api_v1_documents.analyze_route",
                feature="ai_service.analyze_document",
                operation="generation",
                provider="gemini",
                model="gemini-2.5-flash",
                provider_call_index=1,
                prompt_characters=4000,
                input_tokens=1000,
                output_tokens=100,
                thinking_tokens=50,
                cached_input_tokens=0,
                total_tokens=1150,
                input_cost_usd=Decimal("0.000300"),
                output_cost_usd=Decimal("0.000375"),
                total_cost_usd=Decimal("0.000675"),
                pricing_source="test",
                latency_ms=100,
                success=True,
                usage_json="{}",
            ),
            AIUsageEvent(
                user_id=user,
                request_id="req-analysis",
                endpoint="api_v1_documents.analyze_route",
                feature="document_chunk_embedding",
                operation="embedding",
                provider="gemini",
                model="gemini-embedding-2",
                provider_call_index=2,
                prompt_characters=1000,
                input_tokens=250,
                output_tokens=None,
                thinking_tokens=None,
                cached_input_tokens=None,
                total_tokens=250,
                input_cost_usd=Decimal("0.000050"),
                output_cost_usd=None,
                total_cost_usd=Decimal("0.000050"),
                pricing_source="test",
                latency_ms=50,
                success=True,
                usage_json="{}",
            ),
        ]
        db.session.add_all(rows)
        db.session.commit()

    _login(client)
    response = client.get("/api/v1/ai-usage/summary?days=30")
    assert response.status_code == 200
    payload = response.get_json()
    operation = next(item for item in payload["recent_operations"] if item["request_id"] == "req-analysis")
    assert operation["calls"] == 2
    assert operation["total_tokens"] == 1400
    assert operation["thinking_tokens"] == 50
    assert operation["cost_complete"] is True
    assert operation["known_cost_usd"] == 0.000725
    assert payload["totals"]["operations"] >= 1
    assert payload["totals"]["average_complete_operation_cost_usd"] is not None

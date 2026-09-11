from __future__ import annotations

import sys
from types import SimpleNamespace

from ai.providers.base import ProviderGeneration, ProviderUsage
from services import langsmith_observability_service as observability


def _fake_langsmith(captured: list[dict]):
    counter = {"value": 0}

    def uuid7():
        counter["value"] += 1
        return f"fake-run-{counter['value']}"

    def traceable(**config):
        captured.append({"kind": "decorator", "config": config})

        def decorator(func):
            def wrapped(*args, **kwargs):
                extra = kwargs.pop("langsmith_extra", None)
                processed_inputs = config.get("process_inputs", lambda value: value)({"args": args, "kwargs": kwargs})
                captured.append({"kind": "call", "extra": extra, "inputs": processed_inputs})
                result = func(*args, **kwargs)
                processor = config.get("process_outputs")
                if processor is not None:
                    captured.append({"kind": "outputs", "value": processor(result)})
                elif isinstance(result, dict):
                    captured.append({"kind": "outputs", "value": result})
                return result

            return wrapped

        return decorator

    return SimpleNamespace(traceable=traceable, uuid7=uuid7)


def _enable(monkeypatch, captured: list[dict]):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    monkeypatch.setenv("LANGSMITH_PROJECT", "lifeos-tests")
    monkeypatch.setitem(sys.modules, "langsmith", _fake_langsmith(captured))


def test_status_is_non_secret_and_reports_configuration(monkeypatch):
    captured: list[dict] = []
    _enable(monkeypatch, captured)
    status = observability.langsmith_status()
    assert status["state"] == "enabled"
    assert status["ready"] is True
    assert status["project"] == "lifeos-tests"
    assert status["raw_content_logged"] is False
    assert "test-key" not in str(status)


def test_operation_trace_logs_lengths_not_raw_content(monkeypatch):
    captured: list[dict] = []
    _enable(monkeypatch, captured)
    secret_question = "private student question about exam preparation"

    @observability.trace_lifeos_span(
        name="Test operation",
        feature="test_operation",
        metadata_builder=lambda values: {
            "question_characters": len(str(values.get("question") or "")),
        },
        output_metadata_builder=lambda result: {"answer_characters": len(result)},
    )
    def operation(*, question: str) -> str:
        return "private answer text"

    result = operation(question=secret_question)
    assert result == "private answer text"
    serialized = str(captured)
    assert secret_question not in serialized
    assert "private answer text" not in serialized
    assert "question_characters" in serialized
    assert "answer_characters" in serialized


def test_generation_trace_preserves_exactly_once_provider_call(monkeypatch):
    captured: list[dict] = []
    _enable(monkeypatch, captured)
    calls = {"count": 0}

    def provider_call():
        calls["count"] += 1
        return ProviderGeneration(
            text="sensitive generated answer",
            usage=ProviderUsage(
                input_tokens=100,
                output_tokens=20,
                thinking_tokens=5,
                total_tokens=125,
            ),
        )

    traced = observability.trace_generation_call(
        provider="gemini",
        model="gemini-2.5-flash-lite",
        feature="document_type_detection",
        prompt_characters=3000,
        model_tier="cheap",
        requested_model="gemini-2.5-flash",
        provider_call=provider_call,
    )

    assert calls["count"] == 1
    assert traced.generation.text == "sensitive generated answer"
    assert traced.run_id == "fake-run-1"
    serialized = str(captured)
    assert "sensitive generated answer" not in serialized
    assert "input_tokens" in serialized
    assert "reasoning" in serialized
    assert "lifeos_model_tier" in serialized
    assert "cheap" in serialized
    assert "lifeos_model_routed" in serialized


def test_embedding_trace_preserves_usage_without_content(monkeypatch):
    captured: list[dict] = []
    _enable(monkeypatch, captured)
    calls = {"count": 0}
    response = SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1, 0.2])])

    def provider_call():
        calls["count"] += 1
        return response

    traced = observability.trace_embedding_call(
        provider="gemini",
        model="gemini-embedding-2",
        feature="document_embedding",
        prompt_characters=500,
        provider_call=provider_call,
        usage_builder=lambda _response: ProviderUsage(input_tokens=120, total_tokens=120),
    )

    assert calls["count"] == 1
    assert traced.response is response
    assert traced.usage.input_tokens == 120
    assert traced.run_id == "fake-run-1"
    assert "input_tokens" in str(captured)

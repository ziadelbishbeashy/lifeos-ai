"""Regression coverage for Step 20 limits and cost controls."""

from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter
from werkzeug.datastructures import FileStorage

import ai.provider_router as provider_router
from services.document_embedding_service import DocumentEmbeddingError, _validate_batch_size
from services.pdf_service import PDFResourceLimitError, extract_pdf_text, store_pdf_upload
from services.resource_limit_service import (
    ResourceLimitError,
    effective_context_limit,
    enforce_chunk_count,
    enforce_scope_document_count,
    get_resource_limits,
    guard_embedding_request,
    guard_generation_request,
)
from storage.local import LocalStorage


def _pdf_upload(page_count: int) -> FileStorage:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=200, height=200)
    stream = BytesIO()
    writer.write(stream)
    stream.seek(0)
    return FileStorage(stream=stream, filename="limits.pdf", content_type="application/pdf")


def test_active_limits_can_be_overridden_by_app_config(app):
    with app.app_context():
        app.config.update(
            MAX_CONTENT_LENGTH=7 * 1024 * 1024,
            MAX_PDF_PAGES=42,
            MAX_SCOPE_DOCUMENTS=9,
            MAX_AI_PROMPT_CHARACTERS=9000,
            AI_MAX_GENERATION_CALLS_PER_REQUEST=3,
        )
        limits = get_resource_limits()
        assert limits.max_upload_bytes == 7 * 1024 * 1024
        assert limits.max_pdf_pages == 42
        assert limits.max_scope_documents == 9
        assert limits.max_ai_prompt_characters == 9000
        assert limits.max_generation_calls_per_request == 3


def test_pdf_page_limit_is_enforced_before_extraction_work(app, tmp_path):
    storage = LocalStorage(tmp_path)
    upload = _pdf_upload(2)
    stored = store_pdf_upload(
        upload,
        owner_id=1,
        project_id=None,
        max_bytes=2 * 1024 * 1024,
        storage=storage,
    )

    with pytest.raises(PDFResourceLimitError, match="at most 1 pages"):
        extract_pdf_text(stored.storage_key, storage=storage, max_pages=1)


def test_scope_and_chunk_limits_fail_with_clear_messages(app):
    with app.app_context():
        app.config["MAX_SCOPE_DOCUMENTS"] = 2
        app.config["MAX_CHUNKS_PER_DOCUMENT"] = 10
        with pytest.raises(ResourceLimitError, match="at most 2 documents"):
            enforce_scope_document_count(3, scope_label="collection")
        with pytest.raises(ResourceLimitError, match="more than 10 searchable chunks"):
            enforce_chunk_count(11)


def test_context_limit_is_clamped_to_global_ceiling(app):
    with app.app_context():
        app.config["MAX_RAG_CONTEXT_CHARACTERS"] = 5000
        assert effective_context_limit(18_000) == 5000
        assert effective_context_limit(3000) == 3000


def test_generation_prompt_size_and_call_budget_are_enforced(app):
    app.config["MAX_AI_PROMPT_CHARACTERS"] = 2000
    app.config["AI_MAX_GENERATION_CALLS_PER_REQUEST"] = 2

    with app.test_request_context("/api/test"):
        with pytest.raises(ResourceLimitError, match="Maximum prompt size"):
            guard_generation_request(provider="gemini", model="test", prompt="x" * 2001)

        assert guard_generation_request(provider="gemini", model="test", prompt="one") == 1
        assert guard_generation_request(provider="gemini", model="test", prompt="two") == 2
        with pytest.raises(ResourceLimitError, match="AI-call budget"):
            guard_generation_request(provider="gemini", model="test", prompt="three")

    # A fresh HTTP request must start with a fresh provider budget even when
    # the test fixture keeps the same Flask application context alive.
    with app.test_request_context("/api/test-two"):
        assert guard_generation_request(provider="gemini", model="test", prompt="fresh") == 1


def test_embedding_budget_counts_only_actual_provider_attempts(app):
    app.config["AI_MAX_EMBEDDING_CALLS_PER_REQUEST"] = 2
    app.config["AI_MAX_EMBEDDING_CHARACTERS_PER_REQUEST"] = 1000

    with app.test_request_context("/api/test"):
        assert guard_embedding_request(provider="gemini", model="embed", texts=["abc"]) == 1
        assert guard_embedding_request(provider="gemini", model="embed", texts=["def"]) == 2
        with pytest.raises(ResourceLimitError, match="embedding-call budget"):
            guard_embedding_request(provider="gemini", model="embed", texts=["g"])

    with app.test_request_context("/api/test-two"):
        guard_embedding_request(provider="gemini", model="embed", texts=["x" * 600])
        with pytest.raises(ResourceLimitError, match="embedding-input budget"):
            guard_embedding_request(provider="gemini", model="embed", texts=["y" * 401])


def test_embedding_batch_size_uses_step20_limit(app):
    with app.app_context():
        app.config["MAX_EMBEDDING_BATCH_SIZE"] = 7
        assert _validate_batch_size(7) == 7
        with pytest.raises(DocumentEmbeddingError, match="cannot exceed 7"):
            _validate_batch_size(8)


def test_provider_router_does_not_call_provider_when_prompt_is_over_budget(app, monkeypatch):
    calls = []

    class FakeProvider:
        def __init__(self, api_key):
            calls.append(("init", api_key))

        def generate_text(self, *, model, prompt):
            calls.append(("generate", model, prompt))
            return "should not happen"

    monkeypatch.setitem(provider_router._PROVIDER_FACTORIES, "gemini", FakeProvider)
    monkeypatch.setenv("AI_FALLBACK_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "fallback-key")
    monkeypatch.setenv("OPENAI_MODEL", "fallback-model")

    app.config["MAX_AI_PROMPT_CHARACTERS"] = 2000
    with app.test_request_context("/api/test"):
        with pytest.raises(provider_router.AIProviderBudgetError):
            provider_router.generate_text(
                provider="gemini",
                api_key="primary-key",
                model="primary-model",
                prompt="x" * 2001,
                empty_message="empty",
            )

    assert calls == []


def test_resource_limits_cli_reports_active_policy(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["resource-limits"])
    assert result.exit_code == 0
    assert "Step 20 Resource Limits" in result.output
    assert "max_pdf_pages=" in result.output
    assert "max_generation_calls_per_request=" in result.output
    assert "max_embedding_calls_per_request=" in result.output

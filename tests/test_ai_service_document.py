"""Tests for provider-independent Document Brain analysis."""

import json

import pytest

from services import ai_service
from services.ai_service import (
    AIServiceError,
    MAX_DOCUMENT_ANALYSIS_CHARACTERS,
    analyze_document,
)


def fake_configuration():
    return {
        "provider": "gemini",
        "api_key": "test-key",
        "model": "test-model",
    }


def valid_provider_response() -> str:
    return json.dumps(
        {
            "document_type": (
                "Requirements Document"
            ),
            "title": "LifeOS Requirements",
            "summary": (
                "The document defines the main "
                "LifeOS requirements."
            ),
            "purpose": (
                "Define required system capabilities."
            ),
            "key_points": [
                {
                    "title": "Connected intelligence",
                    "detail": (
                        "LifeOS modules must share context."
                    ),
                    "source": {
                        "page": 2,
                        "section": "Architecture",
                        "evidence": (
                            "All intelligence modules "
                            "share one context."
                        ),
                    },
                }
            ],
            "requirements": [
                {
                    "requirement": (
                        "Support document analysis"
                    ),
                    "details": (
                        "Uploaded PDFs must be understood."
                    ),
                    "source": {
                        "page": 3,
                        "section": "Document Brain",
                        "evidence": (
                            "The system analyses PDFs."
                        ),
                    },
                }
            ],
            "decisions": [],
            "risks": [],
            "deadlines": [],
            "action_items": [
                {
                    "title": (
                        "Implement document analysis"
                    ),
                    "description": (
                        "Build structured PDF analysis."
                    ),
                    "priority": "high",
                    "deadline": None,
                    "source": {
                        "page": 3,
                        "section": "Document Brain",
                        "evidence": (
                            "Build document analysis."
                        ),
                    },
                }
            ],
            "missing_information": [],
        },
        ensure_ascii=False,
    )


def test_analyze_document_uses_provider_and_normalises(
    monkeypatch,
):
    captured = {}

    monkeypatch.setattr(
        ai_service,
        "get_ai_configuration",
        fake_configuration,
    )

    def fake_generate_text(
        provider,
        api_key,
        model,
        prompt,
        empty_message,
    ):
        captured["provider"] = provider
        captured["api_key"] = api_key
        captured["model"] = model
        captured["prompt"] = prompt
        captured["empty_message"] = empty_message

        return valid_provider_response()

    monkeypatch.setattr(
        ai_service,
        "_generate_text",
        fake_generate_text,
    )

    result = analyze_document(
        filename="requirements.pdf",
        extracted_text=(
            "--- Page 1 ---\n"
            "LifeOS project introduction.\n\n"
            "--- Page 3 ---\n"
            "The system analyses PDFs."
        ),
    )

    assert result["success"] is True
    assert result["provider"] == "gemini"
    assert result["model"] == "test-model"

    assert result["analysis"][
        "document_type"
    ] == "Requirements Document"

    assert result["analysis"][
        "action_items"
    ][0]["priority"] == "High"

    assert (
        "requirements.pdf"
        in captured["prompt"]
    )

    assert (
        "--- Page 3 ---"
        in captured["prompt"]
    )

    assert captured["provider"] == "gemini"


def test_markdown_wrapped_json_is_supported(
    monkeypatch,
):
    monkeypatch.setattr(
        ai_service,
        "get_ai_configuration",
        fake_configuration,
    )

    monkeypatch.setattr(
        ai_service,
        "_generate_text",
        lambda **kwargs: (
            "```json\n"
            + valid_provider_response()
            + "\n```"
        ),
    )

    result = analyze_document(
        "document.pdf",
        "--- Page 1 ---\nReadable text.",
    )

    assert result["analysis"]["summary"].startswith(
        "The document defines"
    )


def test_document_without_readable_text_is_rejected():
    with pytest.raises(
        AIServiceError,
        match="does not contain readable text",
    ):
        analyze_document(
            "scan.pdf",
            "   ",
        )


def test_document_without_filename_is_rejected():
    with pytest.raises(
        AIServiceError,
        match="must have a filename",
    ):
        analyze_document(
            "",
            "Readable text",
        )


def test_oversized_document_requires_chunking():
    oversized_text = (
        "x"
        * (
            MAX_DOCUMENT_ANALYSIS_CHARACTERS
            + 1
        )
    )

    with pytest.raises(
        AIServiceError,
        match="too large",
    ):
        analyze_document(
            "large.pdf",
            oversized_text,
        )


def test_invalid_provider_json_is_rejected(
    monkeypatch,
):
    monkeypatch.setattr(
        ai_service,
        "get_ai_configuration",
        fake_configuration,
    )

    monkeypatch.setattr(
        ai_service,
        "_generate_text",
        lambda **kwargs: "not JSON",
    )

    with pytest.raises(
        AIServiceError,
        match="did not contain valid",
    ):
        analyze_document(
            "document.pdf",
            "--- Page 1 ---\nReadable text.",
        )


def test_analysis_without_summary_is_rejected(
    monkeypatch,
):
    monkeypatch.setattr(
        ai_service,
        "get_ai_configuration",
        fake_configuration,
    )

    monkeypatch.setattr(
        ai_service,
        "_generate_text",
        lambda **kwargs: json.dumps(
            {
                "document_type": (
                    "General Reference"
                ),
                "summary": "",
            }
        ),
    )

    with pytest.raises(
        AIServiceError,
        match="incomplete",
    ):
        analyze_document(
            "document.pdf",
            "--- Page 1 ---\nReadable text.",
        )
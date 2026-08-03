"""Tests for grounded document questions through the AI service."""

import json

import pytest

from services import ai_service
from services.ai_service import (
    AIServiceError,
    MAX_DOCUMENT_ANALYSIS_CHARACTERS,
    MAX_QUESTION_CHARACTERS,
    ask_document_question,
)


def fake_configuration():
    return {
        "provider": "gemini",
        "api_key": "test-key",
        "model": "test-model",
    }


def grounded_response():
    return json.dumps(
        {
            "answer": (
                "The system must support grounded "
                "document questions."
            ),
            "found_in_document": True,
            "sources": [
                {
                    "page": 3,
                    "section": "Requirements",
                    "evidence": (
                        "The system must support "
                        "document questions."
                    ),
                }
            ],
        }
    )


def test_document_question_returns_grounded_answer(
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
        captured["prompt"] = prompt
        captured["provider"] = provider

        return grounded_response()

    monkeypatch.setattr(
        ai_service,
        "_generate_text",
        fake_generate_text,
    )

    result = ask_document_question(
        filename="requirements.pdf",
        extracted_text=(
            "--- Page 3 ---\n"
            "The system must support document questions."
        ),
        question=(
            "What type of questions must the system support?"
        ),
    )

    assert result["success"] is True
    assert result["found_in_document"] is True
    assert result["sources"][0]["page"] == 3
    assert result["provider"] == "gemini"

    assert (
        "requirements.pdf"
        in captured["prompt"]
    )

    assert (
        "What type of questions"
        in captured["prompt"]
    )


def test_markdown_json_is_supported(
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
            + grounded_response()
            + "\n```"
        ),
    )

    result = ask_document_question(
        filename="document.pdf",
        extracted_text=(
            "--- Page 1 ---\nReadable content."
        ),
        question="What is mentioned?",
    )

    assert result["found_in_document"] is True


def test_missing_question_is_rejected():
    with pytest.raises(
        AIServiceError,
        match="Enter a question",
    ):
        ask_document_question(
            filename="document.pdf",
            extracted_text="Readable text.",
            question=" ",
        )

def test_document_without_context_is_rejected():
    with pytest.raises(
        AIServiceError,
        match="No relevant document context",
    ):
        ask_document_question(
            filename="requirements.pdf",
            extracted_text="",
            question=(
                "What authentication requirements "
                "are mentioned?"
            ),
        )


def test_long_question_is_rejected():
    with pytest.raises(
        AIServiceError,
        match="question is too long",
    ):
        ask_document_question(
            filename="document.pdf",
            extracted_text="Readable text.",
            question=(
                "x"
                * (
                    MAX_QUESTION_CHARACTERS
                    + 1
                )
            ),
        )


def test_large_document_requires_chunking():
    with pytest.raises(
        AIServiceError,
        match="too large",
    ):
        ask_document_question(
            filename="large.pdf",
            extracted_text=(
                "x"
                * (
                    MAX_DOCUMENT_ANALYSIS_CHARACTERS
                    + 1
                )
            ),
            question="What is this document about?",
        )


def test_invalid_provider_response_is_rejected(
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
        ask_document_question(
            filename="document.pdf",
            extracted_text="Readable text.",
            question="What is mentioned?",
        )


def test_answer_found_without_source_is_rejected(
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
                "answer": "The answer exists.",
                "found_in_document": True,
                "sources": [],
            }
        ),
    )

    with pytest.raises(
        AIServiceError,
        match="incomplete",
    ):
        ask_document_question(
            filename="document.pdf",
            extracted_text="Readable text.",
            question="What is mentioned?",
        )
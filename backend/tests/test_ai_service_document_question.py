"""Tests for AI-powered claim-level document questions."""

import json

import pytest

import services.ai_service as ai_service
from services.ai_service import (
    AIServiceError,
    MAX_DOCUMENT_QUESTION_CONTEXT_CHARACTERS,
    MAX_QUESTION_CHARACTERS,
    ask_document_question,
)


def configure_fake_ai(monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "get_ai_configuration",
        lambda: {
            "provider": "gemini",
            "api_key": "test-api-key",
            "model": "test-model",
        },
    )


def test_document_question_returns_validated_claims(
    monkeypatch,
):
    configure_fake_ai(monkeypatch)

    captured = {}

    def fake_generate_text(**kwargs):
        captured["prompt"] = kwargs["prompt"]

        return json.dumps(
            {
                "answer": "",
                "found_in_document": True,
                "claims": [
                    {
                        "text": (
                            "Users reset passwords through a secure "
                            "email link."
                        ),
                        "source_ids": [1, 3],
                    }
                ],
            }
        )

    monkeypatch.setattr(
        ai_service,
        "_generate_text",
        fake_generate_text,
    )

    result = ask_document_question(
        filename="requirements.pdf",
        extracted_text=(
            "[Source 1 | Page 2 | Account Recovery]\n"
            "Users reset passwords through email."
        ),
        question="How can users recover account access?",
    )

    assert result["found_in_document"] is True
    assert result["claims"] == [
        {
            "text": (
                "Users reset passwords through a secure email link."
            ),
            "source_ids": [1, 3],
        }
    ]
    assert "[Source 1, Source 3]" in result["answer"]
    assert result["provider"] == "gemini"
    assert result["model"] == "test-model"

    assert '"claims"' in captured["prompt"]
    assert "independently verifiable claims" in captured["prompt"]
    assert "[Source 1 | Page 2" in captured["prompt"]


def test_not_found_answer_has_no_claims(
    monkeypatch,
):
    configure_fake_ai(monkeypatch)

    monkeypatch.setattr(
        ai_service,
        "_generate_text",
        lambda **kwargs: json.dumps(
            {
                "answer": "The information was not found.",
                "found_in_document": False,
                "claims": [
                    {
                        "text": "Ignored claim.",
                        "source_ids": [1],
                    }
                ],
            }
        ),
    )

    result = ask_document_question(
        filename="requirements.pdf",
        extracted_text=(
            "[Source 1 | Page 1 | Overview]\n"
            "General project information."
        ),
        question="Which fingerprint device is required?",
    )

    assert result["found_in_document"] is False
    assert result["claims"] == []
    assert result["answer"] == "The information was not found."


def test_document_without_filename_is_rejected():
    with pytest.raises(
        AIServiceError,
        match="must have a filename",
    ):
        ask_document_question(
            filename="",
            extracted_text="Retrieved context.",
            question="What is required?",
        )


def test_document_without_context_is_rejected():
    with pytest.raises(
        AIServiceError,
        match="No relevant document context",
    ):
        ask_document_question(
            filename="requirements.pdf",
            extracted_text="",
            question="What is required?",
        )


def test_empty_question_is_rejected():
    with pytest.raises(
        AIServiceError,
        match="Enter a question",
    ):
        ask_document_question(
            filename="requirements.pdf",
            extracted_text="Retrieved context.",
            question="   ",
        )


def test_question_length_is_limited():
    with pytest.raises(
        AIServiceError,
        match="question is too long",
    ):
        ask_document_question(
            filename="requirements.pdf",
            extracted_text="Retrieved context.",
            question="q" * (
                MAX_QUESTION_CHARACTERS + 1
            ),
        )


def test_retrieval_context_length_is_limited():
    with pytest.raises(
        AIServiceError,
        match="context is too large",
    ):
        ask_document_question(
            filename="requirements.pdf",
            extracted_text="x" * (
                MAX_DOCUMENT_QUESTION_CONTEXT_CHARACTERS
                + 1
            ),
            question="What is required?",
        )


def test_invalid_provider_json_is_rejected(
    monkeypatch,
):
    configure_fake_ai(monkeypatch)

    monkeypatch.setattr(
        ai_service,
        "_generate_text",
        lambda **kwargs: "not valid json",
    )

    with pytest.raises(
        AIServiceError,
        match="valid document-answer data",
    ):
        ask_document_question(
            filename="requirements.pdf",
            extracted_text="Retrieved context.",
            question="What is required?",
        )


def test_found_answer_without_claim_sources_is_rejected(
    monkeypatch,
):
    configure_fake_ai(monkeypatch)

    monkeypatch.setattr(
        ai_service,
        "_generate_text",
        lambda **kwargs: json.dumps(
            {
                "answer": "",
                "found_in_document": True,
                "claims": [
                    {
                        "text": "A supposedly supported claim.",
                        "source_ids": [],
                    }
                ],
            }
        ),
    )

    with pytest.raises(
        AIServiceError,
        match="must cite at least one retrieved source",
    ):
        ask_document_question(
            filename="requirements.pdf",
            extracted_text="Retrieved context.",
            question="What is required?",
        )

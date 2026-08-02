"""Tests for grounded Document Brain answer validation."""

import pytest

from services.document_question_service import (
    DocumentQuestionValidationError,
    normalise_document_answer,
)


def test_valid_grounded_answer_is_normalised():
    result = normalise_document_answer(
        {
            "answer": (
                "The system must support grounded "
                "document questions."
            ),
            "found_in_document": True,
            "sources": [
                {
                    "page": "3",
                    "section": "Requirements",
                    "evidence": (
                        "The system must support "
                        "document questions."
                    ),
                }
            ],
        }
    )

    assert result["found_in_document"] is True
    assert result["sources"][0]["page"] == 3
    assert result["sources"][0][
        "section"
    ] == "Requirements"


def test_non_dictionary_answer_is_rejected():
    with pytest.raises(
        DocumentQuestionValidationError,
        match="must be a JSON object",
    ):
        normalise_document_answer(
            ["invalid"]
        )


def test_missing_answer_text_is_rejected():
    with pytest.raises(
        DocumentQuestionValidationError,
        match="must include answer text",
    ):
        normalise_document_answer(
            {
                "answer": "   ",
                "found_in_document": False,
            }
        )


def test_grounded_answer_requires_source():
    with pytest.raises(
        DocumentQuestionValidationError,
        match="at least one source",
    ):
        normalise_document_answer(
            {
                "answer": "The answer is present.",
                "found_in_document": True,
                "sources": [],
            }
        )


def test_not_found_answer_removes_sources():
    result = normalise_document_answer(
        {
            "answer": (
                "This information was not found "
                "in the document."
            ),
            "found_in_document": False,
            "sources": [
                {
                    "page": 1,
                    "evidence": "Unrelated evidence.",
                }
            ],
        }
    )

    assert result["found_in_document"] is False
    assert result["sources"] == []


def test_invalid_and_duplicate_sources_are_removed():
    result = normalise_document_answer(
        {
            "answer": "The answer is on page two.",
            "found_in_document": True,
            "sources": [
                None,
                "invalid",
                {},
                {
                    "page": 2,
                    "section": "Overview",
                    "evidence": "Supporting text.",
                },
                {
                    "page": 2,
                    "section": "Overview",
                    "evidence": "Supporting text.",
                },
            ],
        }
    )

    assert len(result["sources"]) == 1
    assert result["sources"][0]["page"] == 2


def test_answer_and_sources_are_limited():
    sources = [
        {
            "page": index + 1,
            "section": f"Section {index}",
            "evidence": "Evidence",
        }
        for index in range(20)
    ]

    result = normalise_document_answer(
        {
            "answer": "x" * 10_000,
            "found_in_document": True,
            "sources": sources,
        }
    )

    assert len(result["answer"]) == 4_000
    assert len(result["sources"]) == 6
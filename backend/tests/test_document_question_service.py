"""Tests for claim-level document-answer validation."""

import pytest

from services.document_question_service import (
    DocumentQuestionValidationError,
    MAX_SOURCES_PER_CLAIM,
    normalise_document_answer,
    normalise_source_ids,
)


def test_found_answer_keeps_unique_claim_source_ids():
    result = normalise_document_answer(
        {
            "answer": "Ignored for found answers.",
            "found_in_document": True,
            "claims": [
                {
                    "text": "The system requires secure authentication.",
                    "source_ids": [1, 2, 2, "3"],
                }
            ],
        }
    )

    assert result == {
        "answer": "",
        "found_in_document": True,
        "claims": [
            {
                "text": "The system requires secure authentication.",
                "source_ids": [1, 2, 3],
            }
        ],
    }


def test_invalid_source_ids_are_removed():
    assert normalise_source_ids(
        [0, -1, None, "bad", 2, "3"]
    ) == [2, 3]


def test_source_ids_per_claim_are_limited():
    result = normalise_source_ids(
        list(range(1, MAX_SOURCES_PER_CLAIM + 5))
    )

    assert result == list(
        range(1, MAX_SOURCES_PER_CLAIM + 1)
    )


def test_found_answer_requires_a_supported_claim():
    with pytest.raises(
        DocumentQuestionValidationError,
        match="at least one supported claim",
    ):
        normalise_document_answer(
            {
                "answer": "Supported answer.",
                "found_in_document": True,
                "claims": [],
            }
        )


def test_each_claim_requires_a_retrieved_source():
    with pytest.raises(
        DocumentQuestionValidationError,
        match="must cite at least one retrieved source",
    ):
        normalise_document_answer(
            {
                "found_in_document": True,
                "claims": [
                    {
                        "text": "Unsupported claim.",
                        "source_ids": [],
                    }
                ],
            }
        )


def test_not_found_answer_discards_claims():
    result = normalise_document_answer(
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
    )

    assert result["found_in_document"] is False
    assert result["claims"] == []


def test_not_found_answer_text_is_required():
    with pytest.raises(
        DocumentQuestionValidationError,
        match="not-found response",
    ):
        normalise_document_answer(
            {
                "answer": "   ",
                "found_in_document": False,
                "claims": [],
            }
        )


def test_document_answer_must_be_an_object():
    with pytest.raises(
        DocumentQuestionValidationError,
        match="JSON object",
    ):
        normalise_document_answer(
            ["invalid"]
        )

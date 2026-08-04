"""Tests for grounded document-answer validation."""

import pytest

from services.document_question_service import (
    DocumentQuestionValidationError,
    MAX_SOURCES,
    normalise_document_answer,
    normalise_source_ids,
)


def test_found_answer_keeps_unique_source_ids():
    result = normalise_document_answer(
        {
            "answer": "The system requires secure authentication.",
            "found_in_document": True,
            "source_ids": [1, 2, 2, "3"],
        }
    )

    assert result == {
        "answer": "The system requires secure authentication.",
        "found_in_document": True,
        "source_ids": [1, 2, 3],
    }


def test_invalid_source_ids_are_removed():
    assert normalise_source_ids(
        [0, -1, None, "bad", 2, "3"]
    ) == [2, 3]


def test_source_ids_are_limited():
    result = normalise_source_ids(
        list(range(1, MAX_SOURCES + 5))
    )

    assert result == list(
        range(1, MAX_SOURCES + 1)
    )


def test_found_answer_requires_a_retrieved_source():
    with pytest.raises(
        DocumentQuestionValidationError,
        match="at least one retrieved source",
    ):
        normalise_document_answer(
            {
                "answer": "Supported answer.",
                "found_in_document": True,
                "source_ids": [],
            }
        )


def test_not_found_answer_discards_source_ids():
    result = normalise_document_answer(
        {
            "answer": "The information was not found.",
            "found_in_document": False,
            "source_ids": [1, 2],
        }
    )

    assert result["found_in_document"] is False
    assert result["source_ids"] == []


def test_answer_text_is_required():
    with pytest.raises(
        DocumentQuestionValidationError,
        match="include answer text",
    ):
        normalise_document_answer(
            {
                "answer": "   ",
                "found_in_document": False,
                "source_ids": [],
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
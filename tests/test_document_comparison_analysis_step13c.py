"""Step 13C comparison-draft normalization tests."""

import pytest

from services.document_comparison_analysis_service import (
    DocumentComparisonDraftValidationError,
    normalise_document_comparison_draft,
)


def test_comparison_draft_normalises_categories_and_source_prefixes():
    result = normalise_document_comparison_draft(
        {
            "summary": "Two material differences.",
            "findings": [
                {
                    "category": "conflict",
                    "topic": "Release date",
                    "explanation": "The documents give different dates.",
                    "confidence": "high",
                    "document_a": {
                        "statement": "August 15",
                        "source_ids": ["A2", "B99", "A2"],
                    },
                    "document_b": {
                        "statement": "August 28",
                        "source_ids": ["B4"],
                    },
                }
            ],
        }
    )

    finding = result["findings"][0]

    assert finding["category"] == "potential_conflict"
    assert finding["confidence"] == "High"
    assert finding["document_a"]["source_ids"] == ["A2"]
    assert finding["document_b"]["source_ids"] == ["B4"]


def test_empty_findings_are_valid_no_material_difference_result():
    result = normalise_document_comparison_draft(
        {
            "summary": "",
            "findings": [],
        }
    )

    assert result["findings"] == []
    assert "No material differences" in result["summary"]


def test_unknown_difference_category_is_rejected():
    with pytest.raises(
        DocumentComparisonDraftValidationError
    ):
        normalise_document_comparison_draft(
            {
                "summary": "Bad category",
                "findings": [
                    {
                        "category": "probably_similar",
                        "topic": "Scope",
                        "explanation": "Unsupported.",
                    }
                ],
            }
        )

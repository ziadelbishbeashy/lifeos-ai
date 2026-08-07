"""Tests for the Step 5 structured document overview."""

from types import SimpleNamespace

from services.document_analysis_service import (
    DOCUMENT_ANALYSIS_SCHEMA_VERSION,
)
from services.document_overview_service import (
    build_structured_document_overview,
)


def test_overview_builds_counts_from_canonical_analysis():
    analysis = SimpleNamespace(
        summary="A structured project document.",
        document_type="Project Plan",
        insights={
            "summary": "A structured project document.",
            "document_type": "Project Plan",
            "key_points": [
                {
                    "title": "Phased delivery",
                    "detail": "Delivery is split into phases.",
                }
            ],
            "requirements": [
                {
                    "requirement": "Authentication",
                    "details": "Authentication is required.",
                }
            ],
            "decisions": [],
            "risks": [
                {
                    "risk": "Provider availability",
                    "impact": "Analysis may be delayed.",
                }
            ],
            "deadlines": [
                {
                    "date": "2026-08-30",
                    "description": "Complete the first release.",
                }
            ],
            "action_items": [
                {
                    "title": "Prepare deployment checks."
                }
            ],
            "missing_information": [],
            "questions": ["What belongs in the first release?"],
        },
    )

    overview = build_structured_document_overview(
        analysis
    )

    assert overview["schema_version"] == (
        DOCUMENT_ANALYSIS_SCHEMA_VERSION
    )
    assert overview["section_counts"]["key_points"] == 1
    assert overview["section_counts"]["requirements"] == 1
    assert overview["section_counts"]["questions"] == 1
    assert overview["total_items"] == 6
    assert overview["attention_items"] == 2
    assert overview["populated_section_count"] == 6
    assert overview["summary_only"] is False


def test_legacy_analysis_uses_model_columns_and_mixed_formats():
    analysis = SimpleNamespace(
        summary="Saved legacy summary.",
        document_type="Technical Documentation",
        insights={
            "main_points": "The API uses ownership checks.",
            "needs": {
                "title": "Protect document access",
                "description": "Filter every query by the current user.",
            },
            "suggested_questions": [
                "How is access ownership enforced?"
            ],
        },
    )

    overview = build_structured_document_overview(
        analysis
    )

    structured = overview["analysis"]

    assert structured["summary"] == "Saved legacy summary."
    assert structured["document_type"] == (
        "Technical Documentation"
    )
    assert structured["key_points"][0]["title"] == (
        "The API uses ownership checks."
    )
    assert structured["requirements"][0]["requirement"] == (
        "Protect document access"
    )
    assert structured["questions"][0]["question"] == (
        "How is access ownership enforced?"
    )


def test_invalid_legacy_payload_falls_back_to_saved_summary():
    analysis = SimpleNamespace(
        summary="Readable saved summary.",
        document_type="General Reference",
        insights=["invalid", "legacy", "payload"],
    )

    overview = build_structured_document_overview(
        analysis
    )

    assert overview["analysis"]["summary"] == (
        "Readable saved summary."
    )
    assert overview["summary_only"] is True
    assert overview["total_items"] == 0


def test_none_analysis_returns_safe_empty_overview():
    overview = build_structured_document_overview(
        None
    )

    assert overview["analysis"] == {}
    assert overview["total_items"] == 0
    assert overview["total_section_count"] == 8

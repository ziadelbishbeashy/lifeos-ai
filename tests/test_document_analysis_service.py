"""Tests for structured Document Brain analysis validation."""

import pytest

from services.document_analysis_service import (
    DocumentAnalysisValidationError,
    clean_iso_date,
    clean_page_number,
    clean_priority,
    normalise_document_analysis,
)


def test_valid_document_analysis_is_normalised():
    raw_analysis = {
        "document_type": "Requirements Document",
        "title": "LifeOS Requirements",
        "summary": (
            "The document defines the main LifeOS modules "
            "and project requirements."
        ),
        "purpose": (
            "Describe the system features and expected project work."
        ),
        "key_points": [
            {
                "title": "Connected workspace",
                "detail": (
                    "Projects, tasks, notes and documents must "
                    "share information."
                ),
                "source": {
                    "page": 2,
                    "section": "System Overview",
                    "evidence": (
                        "All workspace modules should operate "
                        "as one connected system."
                    ),
                },
            }
        ],
        "requirements": [
            {
                "requirement": "Support PDF analysis",
                "details": (
                    "Users must be able to upload and analyse PDFs."
                ),
                "source": {
                    "page": 4,
                    "section": "Document Brain",
                    "evidence": (
                        "The system shall analyse uploaded PDF files."
                    ),
                },
            }
        ],
        "decisions": [
            {
                "decision": "Use a shared context service",
                "reason": (
                    "All AI features must use the same project data."
                ),
                "source": {
                    "page": 6,
                    "section": "Architecture",
                    "evidence": (
                        "A central context service will serve all "
                        "intelligence features."
                    ),
                },
            }
        ],
        "risks": [
            {
                "risk": "Duplicate generated tasks",
                "impact": (
                    "The project could contain repeated work items."
                ),
                "source": {
                    "page": 8,
                    "section": "Risks",
                    "evidence": (
                        "Generated tasks must be compared with "
                        "existing tasks."
                    ),
                },
            }
        ],
        "deadlines": [
            {
                "date": "2026-08-15",
                "description": (
                    "Complete authentication testing."
                ),
                "source": {
                    "page": 9,
                    "section": "Schedule",
                    "evidence": (
                        "Authentication testing must finish "
                        "before 15 August 2026."
                    ),
                },
            }
        ],
        "action_items": [
            {
                "title": "Build PDF upload",
                "description": (
                    "Create secure PDF upload and validation."
                ),
                "priority": "high",
                "deadline": "2026-08-10",
                "source": {
                    "page": 4,
                    "section": "Document Brain",
                    "evidence": "Add secure PDF upload support.",
                },
            }
        ],
        "missing_information": [
            {
                "question": (
                    "Which OCR provider should be used?"
                ),
                "why_it_matters": (
                    "Scanned documents need a defined OCR strategy."
                ),
                "source": {
                    "page": 10,
                    "section": "Open Questions",
                    "evidence": (
                        "The OCR implementation is not yet selected."
                    ),
                },
            }
        ],
    }

    result = normalise_document_analysis(raw_analysis)

    assert result["document_type"] == (
        "Requirements Document"
    )
    assert result["title"] == "LifeOS Requirements"
    assert result["summary"].startswith(
        "The document defines"
    )

    assert result["requirements"][0] == {
        "requirement": "Support PDF analysis",
        "details": (
            "Users must be able to upload and analyse PDFs."
        ),
        "source": {
            "page": 4,
            "section": "Document Brain",
            "evidence": (
                "The system shall analyse uploaded PDF files."
            ),
        },
    }

    assert result["deadlines"][0]["date"] == (
        "2026-08-15"
    )

    assert result["action_items"][0]["priority"] == (
        "High"
    )
    assert result["action_items"][0]["deadline"] == (
        "2026-08-10"
    )


def test_non_dictionary_analysis_is_rejected():
    with pytest.raises(
        DocumentAnalysisValidationError,
        match="must be a JSON object",
    ):
        normalise_document_analysis(
            ["not", "a", "dictionary"]
        )


def test_analysis_without_summary_is_rejected():
    with pytest.raises(
        DocumentAnalysisValidationError,
        match="must include a summary",
    ):
        normalise_document_analysis(
            {
                "document_type": "Research Paper",
                "summary": "   ",
            }
        )


def test_unknown_document_type_becomes_general_reference():
    result = normalise_document_analysis(
        {
            "document_type": "Random Unknown Type",
            "summary": "This is a valid summary.",
        }
    )

    assert result["document_type"] == (
        "General Reference"
    )


def test_invalid_dates_are_removed():
    result = normalise_document_analysis(
        {
            "summary": "Document summary.",
            "deadlines": [
                {
                    "date": "15-08-2026",
                    "description": "Finish testing.",
                },
                {
                    "date": "2026-08-15",
                    "description": "Submit final version.",
                },
            ],
            "action_items": [
                {
                    "title": "Prepare deployment",
                    "deadline": "tomorrow",
                }
            ],
        }
    )

    assert result["deadlines"][0]["date"] is None
    assert result["deadlines"][1]["date"] == (
        "2026-08-15"
    )
    assert result["action_items"][0][
        "deadline"
    ] is None


def test_invalid_priorities_use_medium():
    result = normalise_document_analysis(
        {
            "summary": "Document summary.",
            "action_items": [
                {
                    "title": "First action",
                    "priority": "urgent",
                },
                {
                    "title": "Second action",
                    "priority": "low",
                },
            ],
        }
    )

    assert result["action_items"][0]["priority"] == (
        "Medium"
    )
    assert result["action_items"][1]["priority"] == (
        "Low"
    )


def test_invalid_page_numbers_become_none():
    result = normalise_document_analysis(
        {
            "summary": "Document summary.",
            "requirements": [
                {
                    "requirement": "First requirement",
                    "details": "Some details.",
                    "source": {
                        "page": -2,
                    },
                },
                {
                    "requirement": "Second requirement",
                    "details": "More details.",
                    "source": {
                        "page": "5",
                    },
                },
            ],
        }
    )

    assert result["requirements"][0][
        "source"
    ]["page"] is None

    assert result["requirements"][1][
        "source"
    ]["page"] == 5


def test_invalid_list_items_are_ignored():
    result = normalise_document_analysis(
        {
            "summary": "Document summary.",
            "requirements": [
                None,
                "plain text",
                {},
                {
                    "requirement": "",
                    "details": "",
                },
                {
                    "requirement": "Valid requirement",
                    "details": "Valid details",
                },
            ],
            "action_items": [
                None,
                {},
                {
                    "description": "Missing title",
                },
                {
                    "title": "Valid action",
                },
            ],
        }
    )

    assert len(result["requirements"]) == 1
    assert result["requirements"][0][
        "requirement"
    ] == "Valid requirement"

    assert len(result["action_items"]) == 1
    assert result["action_items"][0][
        "title"
    ] == "Valid action"


def test_analysis_limits_large_lists():
    requirements = [
        {
            "requirement": f"Requirement {index}",
            "details": "Details",
        }
        for index in range(30)
    ]

    actions = [
        {
            "title": f"Action {index}",
        }
        for index in range(30)
    ]

    result = normalise_document_analysis(
        {
            "summary": "Document summary.",
            "requirements": requirements,
            "action_items": actions,
        }
    )

    assert len(result["requirements"]) == 12
    assert len(result["action_items"]) == 12


def test_long_text_is_truncated():
    result = normalise_document_analysis(
        {
            "summary": "x" * 5000,
            "title": "y" * 500,
            "purpose": "z" * 2000,
        }
    )

    assert len(result["summary"]) == 3000
    assert len(result["title"]) == 300
    assert len(result["purpose"]) == 1200


def test_helper_cleaners():
    assert clean_page_number("7") == 7
    assert clean_page_number(0) is None
    assert clean_page_number("invalid") is None

    assert clean_priority("HIGH") == "High"
    assert clean_priority("urgent") == "Medium"

    assert clean_iso_date("2026-08-15") == (
        "2026-08-15"
    )
    assert clean_iso_date("15/08/2026") is None
    assert clean_iso_date(None) is None
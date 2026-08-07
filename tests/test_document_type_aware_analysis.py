"""Step 6D tests for confirmed-type-aware document analysis."""

import json

import pytest

from services import ai_service
from services.document_analysis_service import (
    DocumentAnalysisValidationError,
    normalise_document_analysis,
)
from services.document_type_profile_service import (
    get_document_type_profile,
)


def fake_configuration():
    return {
        "provider": "gemini",
        "api_key": "test-key",
        "model": "test-model",
    }


def research_response():
    return {
        "document_type": "Research Paper",
        "title": "Grounded RAG Study",
        "summary": "The paper evaluates a grounded retrieval workflow.",
        "purpose": "Evaluate retrieval and citation quality.",
        "key_points": [],
        "requirements": [],
        "decisions": [],
        "risks": [],
        "deadlines": [],
        "action_items": [],
        "missing_information": [],
        "questions": [],
        "type_specific": {
            "research_problem": {
                "text": "Grounding failures reduce answer reliability.",
                "source": {
                    "page": 2,
                    "section": "Introduction",
                    "evidence": "Grounding failures reduce reliability.",
                },
            },
            "objectives": [
                {
                    "text": "Measure citation accuracy.",
                    "detail": "The evaluation compares cited evidence.",
                    "source": {
                        "page": 3,
                        "section": "Objectives",
                        "evidence": "We measure citation accuracy.",
                    },
                }
            ],
            "methodology": [
                {
                    "text": "Hybrid retrieval evaluation",
                    "detail": "BM25 and semantic retrieval are compared.",
                    "source": {
                        "page": 4,
                        "section": "Method",
                        "evidence": "We compare BM25 and semantic retrieval.",
                    },
                }
            ],
            "dataset_or_participants": [],
            "findings": [],
            "limitations": [],
            "research_gaps": [],
            "future_work": [],
            "invented_extra_field": [
                {
                    "text": "Must be discarded."
                }
            ],
        },
    }


def test_confirmed_research_type_drives_specialized_prompt(
    monkeypatch,
):
    captured = {}

    monkeypatch.setattr(
        ai_service,
        "get_ai_configuration",
        fake_configuration,
    )

    def fake_generate_text(**kwargs):
        captured["prompt"] = kwargs["prompt"]
        return json.dumps(
            research_response()
        )

    monkeypatch.setattr(
        ai_service,
        "_generate_text",
        fake_generate_text,
    )

    result = ai_service.analyze_document(
        filename="paper.pdf",
        extracted_text="--- Page 1 ---\nResearch content.",
        confirmed_document_type="research_paper",
    )

    analysis = result["analysis"]

    assert analysis["document_type_key"] == "research_paper"
    assert analysis["document_type"] == "Research Paper"

    assert (
        "CONFIRMED DOCUMENT TYPE:\nResearch Paper"
        in captured["prompt"]
    )

    assert "research_problem" in captured["prompt"]
    assert "methodology" in captured["prompt"]
    assert "research_gaps" in captured["prompt"]

    assert (
        analysis["type_specific"]["research_problem"]["text"]
        == "Grounding failures reduce answer reliability."
    )

    assert (
        "invented_extra_field"
        not in analysis["type_specific"]
    )


def test_confirmed_type_rejects_provider_type_drift():
    raw = research_response()
    raw["document_type"] = "Meeting Notes"

    with pytest.raises(
        DocumentAnalysisValidationError,
        match="did not follow the confirmed",
    ):
        normalise_document_analysis(
            raw,
            confirmed_document_type="research_paper",
        )


def test_specialized_output_contains_only_profile_keys():
    result = normalise_document_analysis(
        research_response(),
        confirmed_document_type="research_paper",
    )

    expected_keys = {
        section.key
        for section in get_document_type_profile(
            "research_paper"
        ).sections
    }

    assert set(
        result["type_specific"]
    ) == expected_keys


def test_missing_specialized_sections_are_empty_not_invented():
    raw = research_response()
    raw["type_specific"] = {}

    result = normalise_document_analysis(
        raw,
        confirmed_document_type="research_paper",
    )

    assert result["type_specific"]["research_problem"] == {
        "text": "",
        "source": {
            "page": None,
            "section": "",
            "evidence": "",
        },
    }

    assert result["type_specific"]["methodology"] == []


def test_unsupported_confirmed_type_is_rejected_before_provider(
    monkeypatch,
):
    monkeypatch.setattr(
        ai_service,
        "get_ai_configuration",
        lambda: pytest.fail(
            "Provider configuration should not be loaded."
        ),
    )

    with pytest.raises(
        ai_service.AIServiceError,
        match="confirmed document type is unsupported",
    ):
        ai_service.analyze_document(
            filename="file.pdf",
            extracted_text="Readable text.",
            confirmed_document_type="financial_report",
        )


def test_legacy_analysis_call_remains_supported(
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
                "document_type": "General Reference",
                "summary": "A general document summary.",
                "type_specific": {},
            }
        ),
    )

    result = ai_service.analyze_document(
        filename="general.pdf",
        extracted_text="Readable content.",
    )

    assert result["analysis"][
        "document_type"
    ] == "General Reference"

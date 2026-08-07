"""Tests for the adaptive document-type workspace view model."""

from types import SimpleNamespace

from services.document_type_workspace_service import (
    build_document_type_workspace,
)


def research_analysis():
    return SimpleNamespace(
        document_type="Research Paper",
        insights={
            "document_type_key": "research_paper",
            "document_type": "Research Paper",
            "type_metadata": {
                "detected_type_key": "research_paper",
                "detected_type": "Research Paper",
                "confirmed_type_key": "research_paper",
                "confirmed_type": "Research Paper",
                "source": "detected_confirmed",
                "confidence": "high",
            },
            "type_specific": {
                "research_problem": {
                    "text": "Grounding failures reduce answer reliability.",
                    "source": {
                        "page": 2,
                        "section": "Introduction",
                        "evidence": "Grounding failures reduce reliability.",
                    },
                },
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
                "findings": [],
            },
        },
    )


def test_research_workspace_uses_research_profile():
    workspace = build_document_type_workspace(
        research_analysis()
    )

    assert workspace["active"] is True
    assert workspace["type_key"] == "research_paper"
    assert workspace["type_label"] == "Research Paper"

    labels = {
        section["label"]
        for section in workspace["sections"]
    }

    assert "Research Problem" in labels
    assert "Methodology" in labels
    assert "Limitations" in labels
    assert "Research Gaps" in labels


def test_workspace_counts_only_supported_content():
    workspace = build_document_type_workspace(
        research_analysis()
    )

    assert workspace["populated_section_count"] == 2
    assert workspace["total_items"] == 2
    assert workspace["has_specialized_content"] is True


def test_workspace_preserves_sources():
    workspace = build_document_type_workspace(
        research_analysis()
    )

    problem = next(
        section
        for section in workspace["sections"]
        if section["key"] == "research_problem"
    )

    assert problem["value"]["source"]["page"] == 2
    assert problem["value"]["source"]["section"] == "Introduction"


def test_user_override_is_exposed_to_ui():
    analysis = research_analysis()
    analysis.insights["type_metadata"] = {
        "detected_type_key": "technical_documentation",
        "detected_type": "Technical Documentation",
        "confirmed_type_key": "research_paper",
        "confirmed_type": "Research Paper",
        "source": "user_override",
        "confidence": "medium",
    }

    workspace = build_document_type_workspace(
        analysis
    )

    assert workspace["metadata"]["status_label"] == "Changed by user"
    assert workspace["metadata"]["detected_type"] == "Technical Documentation"
    assert workspace["metadata"]["confidence"] == "medium"


def test_legacy_analysis_remains_safe():
    analysis = SimpleNamespace(
        document_type="Requirements Document",
        insights={
            "summary": "Legacy structured analysis.",
        },
    )

    workspace = build_document_type_workspace(
        analysis
    )

    assert workspace["active"] is True
    assert workspace["type_label"] == "Requirements Document"
    assert workspace["has_specialized_content"] is False
    assert workspace["metadata"]["source"] == "legacy"


def test_none_analysis_returns_empty_workspace():
    workspace = build_document_type_workspace(
        None
    )

    assert workspace["active"] is False
    assert workspace["sections"] == []

"""Canonical view model for the Document Brain overview workspace."""

from __future__ import annotations

from typing import Any

from services.document_analysis_service import (
    DOCUMENT_ANALYSIS_SCHEMA_VERSION,
    DocumentAnalysisValidationError,
    normalise_document_analysis,
)


OVERVIEW_SECTION_KEYS = (
    "key_points",
    "requirements",
    "decisions",
    "risks",
    "deadlines",
    "action_items",
    "missing_information",
    "questions",
)

ATTENTION_SECTION_KEYS = (
    "risks",
    "deadlines",
    "missing_information",
)


def build_structured_document_overview(
    analysis: Any,
) -> dict[str, Any]:
    """Build one stable dashboard structure for new and legacy analyses."""

    if analysis is None:
        return _empty_overview()

    raw_insights = getattr(
        analysis,
        "insights",
        analysis if isinstance(analysis, dict) else {},
    )

    if not isinstance(raw_insights, dict):
        raw_insights = {}

    merged = dict(
        raw_insights
    )

    model_summary = getattr(
        analysis,
        "summary",
        None,
    )

    model_document_type = getattr(
        analysis,
        "document_type",
        None,
    )

    if not merged.get("summary") and model_summary:
        merged["summary"] = model_summary

    if (
        not merged.get("document_type")
        and model_document_type
    ):
        merged["document_type"] = model_document_type

    try:
        normalized = normalise_document_analysis(
            merged
        )

    except DocumentAnalysisValidationError:
        fallback_summary = str(
            model_summary
            or merged.get("summary")
            or "The saved analysis could not be fully structured."
        ).strip()

        normalized = normalise_document_analysis(
            {
                "document_type": (
                    model_document_type
                    or merged.get("document_type")
                    or "General Reference"
                ),
                "summary": fallback_summary,
            }
        )

    section_counts = {
        key: len(
            normalized.get(key) or []
        )
        for key in OVERVIEW_SECTION_KEYS
    }

    populated_sections = tuple(
        key
        for key, count in section_counts.items()
        if count > 0
    )

    empty_sections = tuple(
        key
        for key, count in section_counts.items()
        if count == 0
    )

    total_items = sum(
        section_counts.values()
    )

    attention_items = sum(
        section_counts[key]
        for key in ATTENTION_SECTION_KEYS
    )

    return {
        "schema_version": normalized.get(
            "schema_version",
            DOCUMENT_ANALYSIS_SCHEMA_VERSION,
        ),
        "analysis": normalized,
        "section_counts": section_counts,
        "total_items": total_items,
        "attention_items": attention_items,
        "populated_section_count": len(
            populated_sections
        ),
        "total_section_count": len(
            OVERVIEW_SECTION_KEYS
        ),
        "populated_sections": populated_sections,
        "empty_sections": empty_sections,
        "summary_only": total_items == 0,
    }


def _empty_overview() -> dict[str, Any]:
    """Return a safe empty structure before analysis exists."""

    section_counts = {
        key: 0
        for key in OVERVIEW_SECTION_KEYS
    }

    return {
        "schema_version": DOCUMENT_ANALYSIS_SCHEMA_VERSION,
        "analysis": {},
        "section_counts": section_counts,
        "total_items": 0,
        "attention_items": 0,
        "populated_section_count": 0,
        "total_section_count": len(
            OVERVIEW_SECTION_KEYS
        ),
        "populated_sections": (),
        "empty_sections": OVERVIEW_SECTION_KEYS,
        "summary_only": True,
    }

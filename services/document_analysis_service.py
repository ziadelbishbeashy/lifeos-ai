"""Structured document-understanding rules for Document Brain."""

from __future__ import annotations

from datetime import datetime
from typing import Any


DOCUMENT_TYPES = {
    "Requirements Document",
    "Research Paper",
    "Meeting Notes",
    "Project Plan",
    "Technical Documentation",
    "Lecture Material",
    "Policy or Contract",
    "General Reference",
}

PRIORITY_LEVELS = {
    "Low",
    "Medium",
    "High",
}

MAX_KEY_POINTS = 8
MAX_REQUIREMENTS = 12
MAX_DECISIONS = 8
MAX_DEADLINES = 8
MAX_RISKS = 8
MAX_ACTION_ITEMS = 12
MAX_MISSING_INFORMATION = 8


class DocumentAnalysisValidationError(ValueError):
    """Raised when document analysis data is unusable."""


def clean_text(
    value: Any,
    *,
    max_length: int = 2000,
) -> str:
    """Return safe, compact text with a maximum length."""

    cleaned = " ".join(
        str(value or "").split()
    )

    return cleaned[:max_length]


def clean_page_number(value: Any) -> int | None:
    """Return a valid positive page number."""

    try:
        page_number = int(value)
    except (TypeError, ValueError):
        return None

    if page_number <= 0:
        return None

    return page_number


def clean_priority(
    value: Any,
    *,
    default: str = "Medium",
) -> str:
    """Return a supported LifeOS priority."""

    cleaned = clean_text(
        value,
        max_length=20,
    ).title()

    if cleaned in PRIORITY_LEVELS:
        return cleaned

    return default


def clean_iso_date(value: Any) -> str | None:
    """Keep only valid YYYY-MM-DD dates."""

    cleaned = clean_text(
        value,
        max_length=20,
    )

    if not cleaned:
        return None

    try:
        parsed = datetime.strptime(
            cleaned,
            "%Y-%m-%d",
        )
    except ValueError:
        return None

    return parsed.date().isoformat()


def normalise_document_type(value: Any) -> str:
    """Return a supported document type."""

    cleaned = clean_text(
        value,
        max_length=80,
    )

    if cleaned in DOCUMENT_TYPES:
        return cleaned

    return "General Reference"


def normalise_source(
    value: Any,
) -> dict[str, Any]:
    """Normalise a source reference from the document."""

    source = (
        value
        if isinstance(value, dict)
        else {}
    )

    return {
        "page": clean_page_number(
            source.get("page")
        ),
        "section": clean_text(
            source.get("section"),
            max_length=160,
        ),
        "evidence": clean_text(
            source.get("evidence"),
            max_length=400,
        ),
    }


def normalise_named_items(
    value: Any,
    *,
    name_key: str,
    detail_key: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Normalise structured facts with source references."""

    if not isinstance(value, list):
        return []

    results: list[dict[str, Any]] = []

    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue

        name = clean_text(
            raw_item.get(name_key),
            max_length=300,
        )

        detail = clean_text(
            raw_item.get(detail_key),
            max_length=1200,
        )

        if not name and not detail:
            continue

        results.append(
            {
                name_key: name,
                detail_key: detail,
                "source": normalise_source(
                    raw_item.get("source")
                ),
            }
        )

        if len(results) >= limit:
            break

    return results


def normalise_deadlines(
    value: Any,
) -> list[dict[str, Any]]:
    """Normalise document deadlines."""

    if not isinstance(value, list):
        return []

    deadlines: list[dict[str, Any]] = []

    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue

        description = clean_text(
            raw_item.get("description"),
            max_length=600,
        )

        date_value = clean_iso_date(
            raw_item.get("date")
        )

        if not description:
            continue

        deadlines.append(
            {
                "date": date_value,
                "description": description,
                "source": normalise_source(
                    raw_item.get("source")
                ),
            }
        )

        if len(deadlines) >= MAX_DEADLINES:
            break

    return deadlines


def normalise_action_items(
    value: Any,
) -> list[dict[str, Any]]:
    """Normalise possible work detected inside the document."""

    if not isinstance(value, list):
        return []

    actions: list[dict[str, Any]] = []

    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue

        title = clean_text(
            raw_item.get("title"),
            max_length=240,
        )

        if not title:
            continue

        actions.append(
            {
                "title": title,
                "description": clean_text(
                    raw_item.get("description"),
                    max_length=1200,
                ),
                "priority": clean_priority(
                    raw_item.get("priority")
                ),
                "deadline": clean_iso_date(
                    raw_item.get("deadline")
                ),
                "source": normalise_source(
                    raw_item.get("source")
                ),
            }
        )

        if len(actions) >= MAX_ACTION_ITEMS:
            break

    return actions


def normalise_document_analysis(
    value: Any,
) -> dict[str, Any]:
    """Return a safe structured Document Brain analysis."""

    if not isinstance(value, dict):
        raise DocumentAnalysisValidationError(
            "Document analysis must be a JSON object."
        )

    summary = clean_text(
        value.get("summary"),
        max_length=3000,
    )

    if not summary:
        raise DocumentAnalysisValidationError(
            "Document analysis must include a summary."
        )

    return {
        "document_type": normalise_document_type(
            value.get("document_type")
        ),
        "title": clean_text(
            value.get("title"),
            max_length=300,
        ),
        "summary": summary,
        "purpose": clean_text(
            value.get("purpose"),
            max_length=1200,
        ),
        "key_points": normalise_named_items(
            value.get("key_points"),
            name_key="title",
            detail_key="detail",
            limit=MAX_KEY_POINTS,
        ),
        "requirements": normalise_named_items(
            value.get("requirements"),
            name_key="requirement",
            detail_key="details",
            limit=MAX_REQUIREMENTS,
        ),
        "decisions": normalise_named_items(
            value.get("decisions"),
            name_key="decision",
            detail_key="reason",
            limit=MAX_DECISIONS,
        ),
        "risks": normalise_named_items(
            value.get("risks"),
            name_key="risk",
            detail_key="impact",
            limit=MAX_RISKS,
        ),
        "deadlines": normalise_deadlines(
            value.get("deadlines")
        ),
        "action_items": normalise_action_items(
            value.get("action_items")
        ),
        "missing_information": normalise_named_items(
            value.get("missing_information"),
            name_key="question",
            detail_key="why_it_matters",
            limit=MAX_MISSING_INFORMATION,
        ),
    }
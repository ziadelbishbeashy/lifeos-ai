"""Type-aware view model for the Document Brain analysis workspace."""

from __future__ import annotations

from typing import Any

from services.document_type_profile_service import (
    GENERAL_REFERENCE_TYPE_KEY,
    get_document_type_profile,
    resolve_document_type_key,
)


def build_document_type_workspace(
    analysis: Any,
) -> dict[str, Any]:
    """Build a safe adaptive dashboard model from one saved analysis."""

    if analysis is None:
        return _empty_workspace()

    raw_insights = getattr(
        analysis,
        "insights",
        analysis if isinstance(analysis, dict) else {},
    )

    if not isinstance(raw_insights, dict):
        raw_insights = {}

    raw_type = (
        raw_insights.get("document_type_key")
        or raw_insights.get("document_type")
        or getattr(analysis, "document_type", None)
        or GENERAL_REFERENCE_TYPE_KEY
    )

    type_key = resolve_document_type_key(
        raw_type
    )

    if type_key is None:
        type_key = GENERAL_REFERENCE_TYPE_KEY

    profile = get_document_type_profile(
        type_key
    )

    raw_type_specific = raw_insights.get(
        "type_specific"
    )

    if not isinstance(raw_type_specific, dict):
        raw_type_specific = {}

    sections: list[dict[str, Any]] = []
    total_items = 0
    populated_count = 0

    for section in profile.sections:
        raw_value = raw_type_specific.get(
            section.key
        )

        if section.value_kind == "text":
            value = _normalise_text_section(
                raw_value
            )

            count = (
                1
                if value["text"]
                else 0
            )

            preview = value["text"]
            items: list[dict[str, Any]] = []

        else:
            items = _normalise_item_section(
                raw_value
            )

            count = len(
                items
            )

            preview = (
                items[0]["text"]
                if items
                else ""
            )

            value = None

        populated = count > 0

        if populated:
            populated_count += 1
            total_items += count

        sections.append(
            {
                "key": section.key,
                "label": section.label,
                "description": section.description,
                "value_kind": section.value_kind,
                "value": value,
                "items": items,
                "count": count,
                "populated": populated,
                "preview": preview,
            }
        )

    raw_metadata = raw_insights.get(
        "type_metadata"
    )

    metadata = _normalise_type_metadata(
        raw_metadata,
        confirmed_type_key=type_key,
    )

    populated_sections = [
        section
        for section in sections
        if section["populated"]
    ]

    return {
        "active": True,
        "type_key": type_key,
        "type_label": profile.label,
        "description": profile.description,
        "metadata": metadata,
        "sections": sections,
        "populated_sections": populated_sections,
        "has_specialized_content": bool(
            populated_sections
        ),
        "populated_section_count": populated_count,
        "total_section_count": len(
            sections
        ),
        "total_items": total_items,
        "spotlight_sections": populated_sections[:4],
    }


def _normalise_type_metadata(
    value: Any,
    *,
    confirmed_type_key: str,
) -> dict[str, Any]:
    """Return user-facing detection/confirmation metadata."""

    raw = (
        value
        if isinstance(value, dict)
        else {}
    )

    source = str(
        raw.get("source") or ""
    ).strip().casefold()

    if source not in {
        "detected_confirmed",
        "user_override",
        "user_confirmed",
    }:
        source = "legacy"

    detected_key = resolve_document_type_key(
        raw.get("detected_type_key")
        or raw.get("detected_type")
    )

    confidence = str(
        raw.get("confidence") or ""
    ).strip().casefold()

    if confidence not in {
        "low",
        "medium",
        "high",
    }:
        confidence = ""

    if source == "detected_confirmed":
        status_label = "Detected and confirmed"
    elif source == "user_override":
        status_label = "Changed by user"
    elif source == "user_confirmed":
        status_label = "Confirmed by user"
    else:
        status_label = "Saved analysis"

    return {
        "source": source,
        "status_label": status_label,
        "detected_type_key": detected_key,
        "detected_type": str(
            raw.get("detected_type") or ""
        ).strip(),
        "confirmed_type_key": confirmed_type_key,
        "confirmed_type": str(
            raw.get("confirmed_type") or ""
        ).strip(),
        "confidence": confidence,
    }


def _normalise_text_section(
    value: Any,
) -> dict[str, Any]:
    """Return a stable type-specific text section."""

    if isinstance(value, dict):
        text = str(
            value.get("text") or ""
        ).strip()

        source = _normalise_source(
            value.get("source")
        )

    else:
        text = str(
            value or ""
        ).strip()

        source = _normalise_source(
            None
        )

    return {
        "text": text,
        "source": source,
    }


def _normalise_item_section(
    value: Any,
) -> list[dict[str, Any]]:
    """Return stable type-specific list items."""

    if not isinstance(value, list):
        return []

    results: list[dict[str, Any]] = []

    for raw_item in value:
        if isinstance(raw_item, dict):
            text = str(
                raw_item.get("text") or ""
            ).strip()

            detail = str(
                raw_item.get("detail") or ""
            ).strip()

            source = _normalise_source(
                raw_item.get("source")
            )

        else:
            text = str(
                raw_item or ""
            ).strip()

            detail = ""
            source = _normalise_source(
                None
            )

        if not text and not detail:
            continue

        results.append(
            {
                "text": text,
                "detail": detail,
                "source": source,
            }
        )

    return results


def _normalise_source(
    value: Any,
) -> dict[str, Any]:
    """Return a safe source dictionary for the existing source macro."""

    raw = (
        value
        if isinstance(value, dict)
        else {}
    )

    page = raw.get("page")

    try:
        page = int(page) if page is not None else None
    except (TypeError, ValueError):
        page = None

    if page is not None and page < 1:
        page = None

    return {
        "page": page,
        "section": str(
            raw.get("section") or ""
        ).strip(),
        "evidence": str(
            raw.get("evidence") or ""
        ).strip(),
    }


def _empty_workspace() -> dict[str, Any]:
    """Return a safe view model before an analysis exists."""

    return {
        "active": False,
        "type_key": None,
        "type_label": "",
        "description": "",
        "metadata": {
            "source": "",
            "status_label": "",
            "detected_type_key": None,
            "detected_type": "",
            "confirmed_type_key": None,
            "confirmed_type": "",
            "confidence": "",
        },
        "sections": [],
        "populated_sections": [],
        "has_specialized_content": False,
        "populated_section_count": 0,
        "total_section_count": 0,
        "total_items": 0,
        "spotlight_sections": [],
    }

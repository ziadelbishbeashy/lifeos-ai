"""Structured document-understanding rules for Document Brain."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from services.document_type_profile_service import (
    get_document_type_label,
    get_document_type_profile,
    resolve_document_type_key,
    supported_document_type_labels,
)


DOCUMENT_ANALYSIS_SCHEMA_VERSION = "document-type-aware-analysis-v3"

# Backwards-compatible public constant. Step 6 keeps the canonical
# type definitions in document_type_profile_service.py.
DOCUMENT_TYPES = set(
    supported_document_type_labels()
)

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
MAX_QUESTIONS = 8
MAX_TYPE_SPECIFIC_ITEMS = 12
MAX_TYPE_SPECIFIC_TEXT_CHARACTERS = 2400


class DocumentAnalysisValidationError(ValueError):
    """Raised when document analysis data is unusable."""


def clean_text(
    value: Any,
    *,
    max_length: int = 2000,
) -> str:
    """Return safe compact text from strings, lists or simple objects."""

    if value is None:
        return ""

    if isinstance(value, str):
        raw_text = value

    elif isinstance(value, (int, float, bool)):
        raw_text = str(value)

    elif isinstance(value, (list, tuple, set)):
        parts = [
            clean_text(
                item,
                max_length=max_length,
            )
            for item in value
        ]

        raw_text = "; ".join(
            part
            for part in parts
            if part
        )

    elif isinstance(value, dict):
        preferred_keys = (
            "text",
            "title",
            "name",
            "summary",
            "description",
            "detail",
            "details",
            "value",
            "question",
        )

        preferred_value = next(
            (
                value.get(key)
                for key in preferred_keys
                if value.get(key) not in (None, "")
            ),
            None,
        )

        if preferred_value is not None:
            raw_text = clean_text(
                preferred_value,
                max_length=max_length,
            )
        else:
            parts = [
                clean_text(
                    nested_value,
                    max_length=max_length,
                )
                for nested_value in value.values()
            ]

            raw_text = "; ".join(
                part
                for part in parts
                if part
            )

    else:
        raw_text = str(value)

    cleaned = " ".join(
        raw_text.split()
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
    """Return the canonical user-facing document type label."""

    return get_document_type_label(
        value
    )


def _first_value(
    data: dict[str, Any],
    keys: Iterable[str],
) -> Any:
    """Return the first non-empty value for a set of aliases."""

    for key in keys:
        value = data.get(key)

        if value not in (None, "", [], {}):
            return value

    return None


def _as_items(value: Any) -> list[Any]:
    """Convert one value or a collection into a list."""

    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, (tuple, set)):
        return list(value)

    return [value]


def _section_value(
    data: dict[str, Any],
    primary_key: str,
    aliases: Iterable[str],
) -> tuple[Any, bool]:
    """Return a section value and whether a legacy alias supplied it."""

    primary_value = data.get(
        primary_key
    )

    if primary_value not in (None, "", [], {}):
        allow_scalar = not isinstance(
            primary_value,
            (list, tuple, set),
        )

        return primary_value, allow_scalar

    for alias in aliases:
        alias_value = data.get(
            alias
        )

        if alias_value not in (None, "", [], {}):
            return alias_value, True

    return None, False


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
            _first_value(
                source,
                ("page", "page_number", "page_start"),
            )
        ),
        "section": clean_text(
            _first_value(
                source,
                ("section", "section_title", "heading"),
            ),
            max_length=160,
        ),
        "evidence": clean_text(
            _first_value(
                source,
                ("evidence", "quote", "excerpt", "source_text"),
            ),
            max_length=400,
        ),
    }


def _source_from_item(raw_item: dict[str, Any]) -> dict[str, Any]:
    """Read a nested source or legacy source fields from one item."""

    nested_source = raw_item.get("source")

    if isinstance(nested_source, dict):
        return normalise_source(
            nested_source
        )

    return normalise_source(
        {
            "page": _first_value(
                raw_item,
                ("page", "page_number", "page_start"),
            ),
            "section": _first_value(
                raw_item,
                ("section", "section_title", "heading"),
            ),
            "evidence": _first_value(
                raw_item,
                ("evidence", "quote", "excerpt", "source_text"),
            ),
        }
    )


def normalise_named_items(
    value: Any,
    *,
    name_key: str,
    detail_key: str,
    limit: int,
    allow_scalar: bool = False,
) -> list[dict[str, Any]]:
    """Normalise structured facts with source references."""

    results: list[dict[str, Any]] = []

    name_aliases = (
        name_key,
        "title",
        "name",
        "label",
        "text",
        "question",
    )

    detail_aliases = (
        detail_key,
        "detail",
        "details",
        "description",
        "reason",
        "impact",
        "context",
        "why_it_matters",
    )

    for raw_item in _as_items(value):
        if isinstance(raw_item, dict):
            name = clean_text(
                _first_value(
                    raw_item,
                    name_aliases,
                ),
                max_length=300,
            )

            detail = clean_text(
                _first_value(
                    raw_item,
                    detail_aliases,
                ),
                max_length=1200,
            )

            source = _source_from_item(
                raw_item
            )

        else:
            if not allow_scalar:
                continue

            name = clean_text(
                raw_item,
                max_length=300,
            )

            detail = ""
            source = normalise_source(None)

        if not name and not detail:
            continue

        results.append(
            {
                name_key: name,
                detail_key: detail,
                "source": source,
            }
        )

        if len(results) >= limit:
            break

    return results


def normalise_deadlines(
    value: Any,
    *,
    allow_scalar: bool = False,
) -> list[dict[str, Any]]:
    """Normalise document deadlines."""

    deadlines: list[dict[str, Any]] = []

    for raw_item in _as_items(value):
        if isinstance(raw_item, dict):
            description = clean_text(
                _first_value(
                    raw_item,
                    (
                        "description",
                        "meaning",
                        "title",
                        "text",
                    ),
                ),
                max_length=600,
            )

            date_value = clean_iso_date(
                _first_value(
                    raw_item,
                    ("date", "deadline", "due_date"),
                )
            )

            source = _source_from_item(
                raw_item
            )

        else:
            if not allow_scalar:
                continue

            description = clean_text(
                raw_item,
                max_length=600,
            )
            date_value = None
            source = normalise_source(None)

        if not description:
            continue

        deadlines.append(
            {
                "date": date_value,
                "description": description,
                "source": source,
            }
        )

        if len(deadlines) >= MAX_DEADLINES:
            break

    return deadlines


def normalise_action_tags(value: Any) -> list[str]:
    """Return a small, safe tag list for a suggested task."""

    if value in (None, ""):
        return []

    if isinstance(value, str):
        raw_items = value.replace(";", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = [value]

    tags: list[str] = []
    seen: set[str] = set()

    for raw_tag in raw_items:
        tag = clean_text(raw_tag, max_length=40)
        key = tag.casefold()

        if not tag or key in seen:
            continue

        seen.add(key)
        tags.append(tag)

        if len(tags) >= 6:
            break

    return tags


def normalise_action_items(
    value: Any,
    *,
    allow_scalar: bool = False,
) -> list[dict[str, Any]]:
    """Normalise possible work detected inside the document."""

    actions: list[dict[str, Any]] = []

    for raw_item in _as_items(value):
        if isinstance(raw_item, dict):
            title = clean_text(
                _first_value(
                    raw_item,
                    ("title", "action", "task", "name", "text"),
                ),
                max_length=240,
            )

            description = clean_text(
                _first_value(
                    raw_item,
                    ("description", "details", "detail", "reason"),
                ),
                max_length=1200,
            )

            priority = clean_priority(
                raw_item.get("priority")
            )

            deadline = clean_iso_date(
                _first_value(
                    raw_item,
                    ("deadline", "due_date", "date"),
                )
            )

            tags = normalise_action_tags(
                raw_item.get("tags")
            )

            source = _source_from_item(
                raw_item
            )

        else:
            if not allow_scalar:
                continue

            title = clean_text(
                raw_item,
                max_length=240,
            )
            description = ""
            priority = "Medium"
            deadline = None
            tags = []
            source = normalise_source(None)

        if not title:
            continue

        actions.append(
            {
                "title": title,
                "description": description,
                "priority": priority,
                "deadline": deadline,
                "tags": tags,
                "source": source,
            }
        )

        if len(actions) >= MAX_ACTION_ITEMS:
            break

    return actions


def normalise_questions(
    value: Any,
) -> list[dict[str, Any]]:
    """Normalise useful document-grounded questions to explore."""

    questions: list[dict[str, Any]] = []

    for raw_item in _as_items(value):
        if isinstance(raw_item, dict):
            question = clean_text(
                _first_value(
                    raw_item,
                    ("question", "title", "text", "prompt"),
                ),
                max_length=500,
            )

            reason = clean_text(
                _first_value(
                    raw_item,
                    (
                        "reason",
                        "why_it_matters",
                        "purpose",
                        "description",
                        "detail",
                    ),
                ),
                max_length=900,
            )

            source = _source_from_item(
                raw_item
            )

        else:
            question = clean_text(
                raw_item,
                max_length=500,
            )
            reason = ""
            source = normalise_source(None)

        if not question:
            continue

        questions.append(
            {
                "question": question,
                "reason": reason,
                "source": source,
            }
        )

        if len(questions) >= MAX_QUESTIONS:
            break

    return questions



def _normalise_type_specific_text(
    value: Any,
) -> dict[str, Any]:
    """Normalise one type-specific text section with trusted source metadata."""

    if isinstance(value, dict):
        text = clean_text(
            _first_value(
                value,
                (
                    "text",
                    "summary",
                    "detail",
                    "details",
                    "description",
                    "value",
                    "content",
                ),
            ),
            max_length=MAX_TYPE_SPECIFIC_TEXT_CHARACTERS,
        )

        source = _source_from_item(
            value
        )

    else:
        text = clean_text(
            value,
            max_length=MAX_TYPE_SPECIFIC_TEXT_CHARACTERS,
        )

        source = normalise_source(
            None
        )

    return {
        "text": text,
        "source": source,
    }


def _normalise_type_specific_items(
    value: Any,
) -> list[dict[str, Any]]:
    """Normalise one type-specific list into a stable display shape."""

    results: list[dict[str, Any]] = []

    for raw_item in _as_items(
        value
    ):
        if isinstance(
            raw_item,
            dict,
        ):
            text = clean_text(
                _first_value(
                    raw_item,
                    (
                        "text",
                        "title",
                        "name",
                        "label",
                        "item",
                        "fact",
                        "finding",
                        "value",
                    ),
                ),
                max_length=600,
            )

            detail = clean_text(
                _first_value(
                    raw_item,
                    (
                        "detail",
                        "details",
                        "description",
                        "reason",
                        "context",
                        "impact",
                        "explanation",
                    ),
                ),
                max_length=1400,
            )

            source = _source_from_item(
                raw_item
            )

        else:
            text = clean_text(
                raw_item,
                max_length=600,
            )

            detail = ""
            source = normalise_source(
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

        if len(
            results
        ) >= MAX_TYPE_SPECIFIC_ITEMS:
            break

    return results


def normalise_type_specific_analysis(
    value: Any,
    *,
    document_type_key: str,
) -> dict[str, Any]:
    """
    Return only the specialized fields allowed by the confirmed profile.

    Unknown AI-generated keys are discarded rather than exposed to the UI.
    """

    profile = get_document_type_profile(
        document_type_key
    )

    raw_sections = (
        value
        if isinstance(
            value,
            dict,
        )
        else {}
    )

    normalised: dict[
        str,
        Any,
    ] = {}

    for section in profile.sections:
        raw_value = raw_sections.get(
            section.key
        )

        if section.value_kind == "text":
            normalised[
                section.key
            ] = _normalise_type_specific_text(
                raw_value
            )

        else:
            normalised[
                section.key
            ] = _normalise_type_specific_items(
                raw_value
            )

    return normalised


def _resolve_analysis_document_type(
    value: dict[str, Any],
    *,
    confirmed_document_type: object | None,
) -> tuple[str, str]:
    """Resolve and, when provided, enforce the user-confirmed type."""

    if confirmed_document_type not in (
        None,
        "",
    ):
        confirmed_key = resolve_document_type_key(
            confirmed_document_type
        )

        if confirmed_key is None:
            raise DocumentAnalysisValidationError(
                "The confirmed document type is unsupported."
            )

        provider_type = _first_value(
            value,
            (
                "document_type",
                "type",
                "category",
            ),
        )

        if provider_type not in (
            None,
            "",
        ):
            provider_key = resolve_document_type_key(
                provider_type
            )

            if provider_key is None:
                raise DocumentAnalysisValidationError(
                    "The AI returned an unsupported document type."
                )

            if provider_key != confirmed_key:
                raise DocumentAnalysisValidationError(
                    "The AI analysis did not follow the confirmed "
                    "document type."
                )

        return (
            confirmed_key,
            get_document_type_label(
                confirmed_key
            ),
        )

    legacy_label = normalise_document_type(
        _first_value(
            value,
            (
                "document_type",
                "type",
                "category",
            ),
        )
    )

    legacy_key = resolve_document_type_key(
        legacy_label
    )

    if legacy_key is None:
        legacy_key = "general_reference"

    return (
        legacy_key,
        legacy_label,
    )

def normalise_document_analysis(
    value: Any,
    *,
    confirmed_document_type: object | None = None,
) -> dict[str, Any]:
    """Return a safe canonical and optionally type-aware overview."""

    if not isinstance(value, dict):
        raise DocumentAnalysisValidationError(
            "Document analysis must be a JSON object."
        )

    summary = clean_text(
        _first_value(
            value,
            ("summary", "overview", "executive_summary"),
        ),
        max_length=3000,
    )

    if not summary:
        raise DocumentAnalysisValidationError(
            "Document analysis must include a summary."
        )

    (
        document_type_key,
        document_type_label,
    ) = _resolve_analysis_document_type(
        value,
        confirmed_document_type=confirmed_document_type,
    )

    key_points, key_points_legacy = _section_value(
        value,
        "key_points",
        ("highlights", "main_points"),
    )

    requirements, requirements_legacy = _section_value(
        value,
        "requirements",
        ("needs", "constraints"),
    )

    decisions, decisions_legacy = _section_value(
        value,
        "decisions",
        ("commitments",),
    )

    risks, risks_legacy = _section_value(
        value,
        "risks",
        ("blockers", "issues"),
    )

    deadlines, deadlines_legacy = _section_value(
        value,
        "deadlines",
        ("dates", "milestones"),
    )

    action_items, action_items_legacy = _section_value(
        value,
        "action_items",
        ("actions", "tasks"),
    )

    missing_information, missing_legacy = _section_value(
        value,
        "missing_information",
        ("unclear_information", "open_issues"),
    )

    questions, _questions_legacy = _section_value(
        value,
        "questions",
        (
            "questions_to_explore",
            "suggested_questions",
            "follow_up_questions",
        ),
    )

    return {
        "schema_version": DOCUMENT_ANALYSIS_SCHEMA_VERSION,
        "document_type_key": document_type_key,
        "document_type": document_type_label,
        "title": clean_text(
            _first_value(
                value,
                ("title", "document_title", "name"),
            ),
            max_length=300,
        ),
        "summary": summary,
        "purpose": clean_text(
            _first_value(
                value,
                ("purpose", "objective", "intent"),
            ),
            max_length=1200,
        ),
        "key_points": normalise_named_items(
            key_points,
            name_key="title",
            detail_key="detail",
            limit=MAX_KEY_POINTS,
            allow_scalar=key_points_legacy,
        ),
        "requirements": normalise_named_items(
            requirements,
            name_key="requirement",
            detail_key="details",
            limit=MAX_REQUIREMENTS,
            allow_scalar=requirements_legacy,
        ),
        "decisions": normalise_named_items(
            decisions,
            name_key="decision",
            detail_key="reason",
            limit=MAX_DECISIONS,
            allow_scalar=decisions_legacy,
        ),
        "risks": normalise_named_items(
            risks,
            name_key="risk",
            detail_key="impact",
            limit=MAX_RISKS,
            allow_scalar=risks_legacy,
        ),
        "deadlines": normalise_deadlines(
            deadlines,
            allow_scalar=deadlines_legacy,
        ),
        "action_items": normalise_action_items(
            action_items,
            allow_scalar=action_items_legacy,
        ),
        "missing_information": normalise_named_items(
            missing_information,
            name_key="question",
            detail_key="why_it_matters",
            limit=MAX_MISSING_INFORMATION,
            allow_scalar=missing_legacy,
        ),
        "questions": normalise_questions(
            questions
        ),
        "type_specific": normalise_type_specific_analysis(
            value.get(
                "type_specific"
            ),
            document_type_key=document_type_key,
        ),
    }


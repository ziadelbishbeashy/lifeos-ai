"""Validation rules for grounded Document Brain answers."""

from __future__ import annotations

from typing import Any


MAX_ANSWER_CHARACTERS = 4_000
MAX_SOURCES = 6


class DocumentQuestionValidationError(ValueError):
    """Raised when a document answer is unusable."""


def clean_text(
    value: Any,
    *,
    max_length: int,
) -> str:
    """Return compact text limited to a safe length."""

    cleaned = " ".join(
        str(value or "").split()
    )

    return cleaned[:max_length]


def clean_page_number(
    value: Any,
) -> int | None:
    """Return a valid positive PDF page number."""

    try:
        page = int(value)
    except (TypeError, ValueError):
        return None

    return page if page > 0 else None


def clean_boolean(
    value: Any,
) -> bool:
    """Convert supported boolean values safely."""

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "1",
            "yes",
        }

    return bool(value)
def clean_source_id(
    value: Any,
) -> int | None:
    """Return a valid positive retrieved-source number."""

    try:
        source_id = int(value)

    except (
        TypeError,
        ValueError,
    ):
        return None

    return (
        source_id
        if source_id > 0
        else None
    )


def normalise_source_ids(
    value: Any,
) -> list[int]:
    """Return unique positive retrieved-source numbers."""

    if not isinstance(
        value,
        list,
    ):
        return []

    source_ids: list[int] = []
    seen: set[int] = set()

    for raw_source_id in value:
        source_id = clean_source_id(
            raw_source_id
        )

        if (
            source_id is None
            or source_id in seen
        ):
            continue

        seen.add(
            source_id
        )

        source_ids.append(
            source_id
        )

        if len(source_ids) >= MAX_SOURCES:
            break

    return source_ids

def normalise_answer_source(
    value: Any,
) -> dict[str, Any] | None:
    """Normalise one supporting document reference."""

    if not isinstance(value, dict):
        return None

    page = clean_page_number(
        value.get("page")
    )

    section = clean_text(
        value.get("section"),
        max_length=160,
    )

    evidence = clean_text(
        value.get("evidence"),
        max_length=500,
    )

    if page is None and not section and not evidence:
        return None

    return {
        "page": page,
        "section": section,
        "evidence": evidence,
    }


def normalise_answer_sources(
    value: Any,
) -> list[dict[str, Any]]:
    """Return valid, unique document references."""

    if not isinstance(value, list):
        return []

    sources: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    for raw_source in value:
        source = normalise_answer_source(
            raw_source
        )

        if source is None:
            continue

        identity = (
            source["page"],
            source["section"],
            source["evidence"],
        )

        if identity in seen:
            continue

        seen.add(identity)
        sources.append(source)

        if len(sources) >= MAX_SOURCES:
            break

    return sources


def normalise_document_answer(
    value: Any,
) -> dict[str, Any]:
    """Validate a grounded answer returned by an AI provider."""

    if not isinstance(value, dict):
        raise DocumentQuestionValidationError(
            "The document answer must be a JSON object."
        )

    answer = clean_text(
        value.get("answer"),
        max_length=MAX_ANSWER_CHARACTERS,
    )

    if not answer:
        raise DocumentQuestionValidationError(
            "The document answer must include answer text."
        )

    found_in_document = clean_boolean(
        value.get("found_in_document")
    )

    source_ids = normalise_source_ids(
        value.get("source_ids")
    )

    if found_in_document and not source_ids:
        raise DocumentQuestionValidationError(
            "An answer found in the document must cite "
            "at least one retrieved source."
        )

    if not found_in_document:
        source_ids = []

    return {
        "answer": answer,
        "found_in_document": found_in_document,
        "source_ids": source_ids,
    }
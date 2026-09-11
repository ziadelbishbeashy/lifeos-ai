"""Validation rules for grounded Document Brain answers."""

from __future__ import annotations

from typing import Any


MAX_ANSWER_CHARACTERS = 4_000
MAX_CLAIMS = 8
MAX_CLAIM_CHARACTERS = 800
MAX_SOURCES_PER_CLAIM = 3


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
    except (TypeError, ValueError):
        return None

    return source_id if source_id > 0 else None


def normalise_source_ids(
    value: Any,
) -> list[int]:
    """Return unique positive source numbers for one claim."""

    if not isinstance(value, list):
        return []

    source_ids: list[int] = []
    seen: set[int] = set()

    for raw_source_id in value:
        source_id = clean_source_id(
            raw_source_id
        )

        if source_id is None or source_id in seen:
            continue

        seen.add(source_id)
        source_ids.append(source_id)

        if len(source_ids) >= MAX_SOURCES_PER_CLAIM:
            break

    return source_ids


def normalise_answer_claim(
    value: Any,
    *,
    claim_number: int,
) -> dict[str, Any]:
    """Validate one independently supported answer claim."""

    if not isinstance(value, dict):
        raise DocumentQuestionValidationError(
            f"Claim {claim_number} must be a JSON object."
        )

    text = clean_text(
        value.get("text"),
        max_length=MAX_CLAIM_CHARACTERS,
    )

    if not text:
        raise DocumentQuestionValidationError(
            f"Claim {claim_number} must include text."
        )

    source_ids = normalise_source_ids(
        value.get("source_ids")
    )

    if not source_ids:
        raise DocumentQuestionValidationError(
            f"Claim {claim_number} must cite at least one "
            "retrieved source."
        )

    return {
        "text": text,
        "source_ids": source_ids,
    }


def normalise_answer_claims(
    value: Any,
) -> list[dict[str, Any]]:
    """Validate the bounded list of grounded answer claims."""

    if not isinstance(value, list):
        return []

    claims: list[dict[str, Any]] = []
    seen_text: set[str] = set()

    for index, raw_claim in enumerate(
        value[:MAX_CLAIMS],
        start=1,
    ):
        claim = normalise_answer_claim(
            raw_claim,
            claim_number=index,
        )

        identity = claim["text"].casefold()

        if identity in seen_text:
            continue

        seen_text.add(identity)
        claims.append(claim)

    return claims


def normalise_document_answer(
    value: Any,
) -> dict[str, Any]:
    """Validate a claim-level grounded AI response."""

    if not isinstance(value, dict):
        raise DocumentQuestionValidationError(
            "The document answer must be a JSON object."
        )

    found_in_document = clean_boolean(
        value.get("found_in_document")
    )

    if found_in_document:
        claims = normalise_answer_claims(
            value.get("claims")
        )

        if not claims:
            raise DocumentQuestionValidationError(
                "An answer found in the document must include "
                "at least one supported claim."
            )

        return {
            "answer": "",
            "found_in_document": True,
            "claims": claims,
        }

    answer = clean_text(
        value.get("answer"),
        max_length=MAX_ANSWER_CHARACTERS,
    )

    if not answer:
        raise DocumentQuestionValidationError(
            "A not-found response must include answer text."
        )

    return {
        "answer": answer,
        "found_in_document": False,
        "claims": [],
    }

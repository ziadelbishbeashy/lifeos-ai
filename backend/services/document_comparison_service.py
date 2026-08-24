"""Step 13A foundation for safe two-document comparison.

This module deliberately does not perform semantic comparison yet. It owns the
stable foundation Step 13B-13F will build on:

- ordered document-pair validation
- ownership enforcement
- deterministic source fingerprints
- completed-result reuse/caching
- owned comparison history
- cleanup of saved comparisons before source documents are deleted
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable

from sqlalchemy import or_

from database import db
from models import Document, DocumentComparison
from services.document_access_service import (
    DocumentNotFoundError,
    require_owned_document,
)


DOCUMENT_COMPARISON_SCHEMA_VERSION = (
    "document-comparison-foundation-v1"
)

DEFAULT_COMPARISON_HISTORY_LIMIT = 20
MAX_COMPARISON_HISTORY_LIMIT = 100


class DocumentComparisonError(RuntimeError):
    """Base exception for Step 13 comparison foundation failures."""


class DocumentComparisonValidationError(
    DocumentComparisonError,
    ValueError,
):
    """Raised when a requested document pair is invalid."""


class DocumentComparisonNotFoundError(
    DocumentComparisonError,
    LookupError,
):
    """Raised when a document/comparison is not owned by the requester."""


@dataclass(frozen=True)
class DocumentComparisonFoundation:
    """Validated ordered pair plus its current cache identity."""

    document_a: Document
    document_b: Document
    source_fingerprint: str
    reusable_comparison: DocumentComparison | None


def require_owned_document_pair(
    *,
    owner_id: int,
    document_a_id: Any,
    document_b_id: Any,
) -> tuple[Document, Document]:
    """
    Validate and return an ordered pair of documents owned by one user.

    A and B are intentionally NOT sorted. Direction matters:
    A -> B can classify something as added, while B -> A classifies
    the same information as removed.
    """

    cleaned_a_id = _coerce_document_id(
        document_a_id,
        label="Document A",
    )
    cleaned_b_id = _coerce_document_id(
        document_b_id,
        label="Document B",
    )

    if cleaned_a_id == cleaned_b_id:
        raise DocumentComparisonValidationError(
            "Choose two different documents to compare."
        )

    document_a = _require_owned_comparison_document(
        document_id=cleaned_a_id,
        owner_id=owner_id,
    )

    document_b = _require_owned_comparison_document(
        document_id=cleaned_b_id,
        owner_id=owner_id,
    )

    return (
        document_a,
        document_b,
    )


def create_ordered_comparison_fingerprint(
    *,
    document_a: Document,
    document_b: Document,
) -> str:
    """
    Create a stable SHA-256 cache identity for A -> B.

    The ordered document IDs make A -> B distinct from B -> A.
    The extracted-text hashes invalidate the result when either source changes.
    Filenames are included because comparison output will expose source names.
    """

    payload = {
        "schema_version": DOCUMENT_COMPARISON_SCHEMA_VERSION,
        "document_a": _document_fingerprint_payload(
            document_a
        ),
        "document_b": _document_fingerprint_payload(
            document_b
        ),
    }

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(
        encoded
    ).hexdigest()


def find_reusable_owned_comparison(
    *,
    owner_id: int,
    document_a_id: int,
    document_b_id: int,
    source_fingerprint: str,
) -> DocumentComparison | None:
    """Return the newest exact completed comparison for the ordered pair."""

    cleaned_fingerprint = str(
        source_fingerprint
        or ""
    ).strip()

    if not cleaned_fingerprint:
        return None

    return (
        DocumentComparison.query
        .filter_by(
            user_id=owner_id,
            document_a_id=document_a_id,
            document_b_id=document_b_id,
            status="Completed",
            source_fingerprint=cleaned_fingerprint,
        )
        .order_by(
            DocumentComparison.created_at.desc(),
            DocumentComparison.id.desc(),
        )
        .first()
    )


def prepare_owned_document_comparison(
    *,
    owner_id: int,
    document_a_id: Any,
    document_b_id: Any,
    force: bool = False,
) -> DocumentComparisonFoundation:
    """
    Build the Step 13A comparison foundation for a requested pair.

    No AI provider is called here. Later Step 13 stages can use
    ``reusable_comparison`` when it is present or continue building evidence
    when it is absent.
    """

    document_a, document_b = require_owned_document_pair(
        owner_id=owner_id,
        document_a_id=document_a_id,
        document_b_id=document_b_id,
    )

    source_fingerprint = (
        create_ordered_comparison_fingerprint(
            document_a=document_a,
            document_b=document_b,
        )
    )

    reusable_comparison = None

    if not force:
        reusable_comparison = (
            find_reusable_owned_comparison(
                owner_id=owner_id,
                document_a_id=document_a.id,
                document_b_id=document_b.id,
                source_fingerprint=source_fingerprint,
            )
        )

    return DocumentComparisonFoundation(
        document_a=document_a,
        document_b=document_b,
        source_fingerprint=source_fingerprint,
        reusable_comparison=reusable_comparison,
    )


def require_owned_comparison(
    *,
    comparison_id: Any,
    owner_id: int,
) -> DocumentComparison:
    """Return one saved comparison only when it belongs to the requester."""

    try:
        cleaned_id = int(
            comparison_id
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise DocumentComparisonNotFoundError(
            "The requested comparison was not found."
        ) from error

    if cleaned_id <= 0:
        raise DocumentComparisonNotFoundError(
            "The requested comparison was not found."
        )

    comparison = (
        DocumentComparison.query
        .filter_by(
            id=cleaned_id,
            user_id=owner_id,
        )
        .first()
    )

    if comparison is None:
        raise DocumentComparisonNotFoundError(
            "The requested comparison was not found."
        )

    return comparison


def list_owned_comparisons(
    *,
    owner_id: int,
    limit: int = DEFAULT_COMPARISON_HISTORY_LIMIT,
) -> list[DocumentComparison]:
    """Return newest saved comparisons belonging only to one user."""

    cleaned_limit = _normalise_history_limit(
        limit
    )

    return (
        DocumentComparison.query
        .filter_by(
            user_id=owner_id
        )
        .order_by(
            DocumentComparison.created_at.desc(),
            DocumentComparison.id.desc(),
        )
        .limit(
            cleaned_limit
        )
        .all()
    )


def delete_comparisons_referencing_documents(
    document_ids: Iterable[Any],
) -> int:
    """
    Delete saved comparisons that reference documents about to be removed.

    SQL Server requires the document foreign keys to use ON DELETE NO ACTION
    because A and B both point to ``documents``. Project/document deletion
    therefore calls this helper inside its existing transaction before deleting
    the source rows.
    """

    cleaned_ids = {
        int(document_id)
        for document_id in document_ids
        if _is_positive_integer(
            document_id
        )
    }

    if not cleaned_ids:
        return 0

    return (
        DocumentComparison.query
        .filter(
            or_(
                DocumentComparison.document_a_id.in_(
                    cleaned_ids
                ),
                DocumentComparison.document_b_id.in_(
                    cleaned_ids
                ),
            )
        )
        .delete(
            synchronize_session=False
        )
    )


def _require_owned_comparison_document(
    *,
    document_id: int,
    owner_id: int,
) -> Document:
    try:
        return require_owned_document(
            document_id=document_id,
            owner_id=owner_id,
        )

    except DocumentNotFoundError as error:
        # Use a neutral message so callers cannot distinguish a missing
        # document from another user's document.
        raise DocumentComparisonNotFoundError(
            "One or both selected documents were not found."
        ) from error


def _document_fingerprint_payload(
    document: Document,
) -> dict[str, Any]:
    extracted_text = str(
        document.extracted_text
        or ""
    ).strip()

    text_fingerprint = hashlib.sha256(
        extracted_text.encode("utf-8")
    ).hexdigest()

    return {
        "document_id": document.id,
        "filename": str(
            document.filename
            or ""
        ).strip(),
        "content_sha256": text_fingerprint,
    }


def _coerce_document_id(
    value: Any,
    *,
    label: str,
) -> int:
    try:
        document_id = int(
            value
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise DocumentComparisonValidationError(
            f"{label} is invalid."
        ) from error

    if document_id <= 0:
        raise DocumentComparisonValidationError(
            f"{label} is invalid."
        )

    return document_id


def _normalise_history_limit(
    value: Any,
) -> int:
    try:
        limit = int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        limit = DEFAULT_COMPARISON_HISTORY_LIMIT

    return max(
        1,
        min(
            MAX_COMPARISON_HISTORY_LIMIT,
            limit,
        ),
    )


def _is_positive_integer(
    value: Any,
) -> bool:
    try:
        return int(
            value
        ) > 0
    except (
        TypeError,
        ValueError,
    ):
        return False

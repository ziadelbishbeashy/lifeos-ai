"""User-facing semantic search payloads for the LifeOS PDF viewer.

The retrieval engine remains chunk-based internally. This module deliberately
hides chunk ids, ranks, similarity scores, embedding/provider data, and other
developer details from the browser-facing PDF experience.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.document_search_service import (
    MAX_SEARCH_RESULT_LIMIT,
    DocumentSearchError,
    DocumentSearchNotFoundError,
    DocumentSearchNotReadyError,
    DocumentSearchValidationError,
    search_owned_document,
)


class DocumentPDFSearchError(RuntimeError):
    """Base error for semantic PDF viewer search."""


class DocumentPDFSearchNotFoundError(DocumentPDFSearchError):
    """Raised when the PDF is missing or not owned."""


class DocumentPDFSearchNotReadyError(DocumentPDFSearchError):
    """Raised when the PDF does not have searchable text."""


class DocumentPDFSearchValidationError(DocumentPDFSearchError):
    """Raised when a semantic viewer query is invalid."""


@dataclass(frozen=True)
class DocumentPDFSemanticMatch:
    """One user-facing passage to highlight in the PDF."""

    match_id: str
    page_start: int | None
    page_end: int | None
    page_label: str
    section: str
    text: str
    emphasis: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "page_label": self.page_label,
            "section": self.section,
            "text": self.text,
            "emphasis": self.emphasis,
        }


@dataclass(frozen=True)
class DocumentPDFSemanticSearchResult:
    """Sanitized result returned to the embedded PDF viewer."""

    document: Any
    query: str
    matches: tuple[DocumentPDFSemanticMatch, ...]
    limited: bool
    degraded: bool

    @property
    def result_count(self) -> int:
        return len(self.matches)

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "result_count": self.result_count,
            "limited": self.limited,
            "degraded": self.degraded,
            "matches": [
                match.as_dict()
                for match in self.matches
            ],
        }


def search_owned_document_for_pdf(
    *,
    document_id: int,
    user_id: int,
    query: str,
) -> DocumentPDFSemanticSearchResult:
    """
    Search an owned PDF and expose only information useful to a reader.

    Technical retrieval details stay inside the backend. The PDF viewer gets
    only the real passage, its location, and a coarse visual emphasis level.
    """

    try:
        result = search_owned_document(
            document_id=document_id,
            user_id=user_id,
            query=query,
            limit=MAX_SEARCH_RESULT_LIMIT,
        )

    except DocumentSearchNotFoundError as error:
        raise DocumentPDFSearchNotFoundError(
            str(error)
        ) from error

    except DocumentSearchNotReadyError as error:
        raise DocumentPDFSearchNotReadyError(
            str(error)
        ) from error

    except DocumentSearchValidationError as error:
        raise DocumentPDFSearchValidationError(
            str(error)
        ) from error

    except DocumentSearchError as error:
        raise DocumentPDFSearchError(
            str(error)
        ) from error

    matches: list[DocumentPDFSemanticMatch] = []

    for index, hit in enumerate(
        result.hits,
        start=1,
    ):
        emphasis = (
            "strong"
            if str(hit.match_strength).casefold() in {
                "exact",
                "strong",
            }
            else "related"
        )

        matches.append(
            DocumentPDFSemanticMatch(
                match_id=f"match-{index}",
                page_start=hit.page_start,
                page_end=hit.page_end,
                page_label=hit.page_label,
                section=hit.section,
                text=hit.preview,
                emphasis=emphasis,
            )
        )

    return DocumentPDFSemanticSearchResult(
        document=result.document,
        query=result.query,
        matches=tuple(matches),
        limited=(
            result.result_count
            >= MAX_SEARCH_RESULT_LIMIT
        ),
        degraded=bool(
            result.semantic_fallback
        ),
    )

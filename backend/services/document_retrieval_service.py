"""Keyword retrieval for Document Brain RAG."""

from __future__ import annotations

import math
import re

from collections import Counter
from dataclasses import dataclass

from models import Document, DocumentChunk
from services.document_chunk_service import (
    DocumentChunkError,
    DocumentChunkNotFoundError,
    DocumentChunkNotReadyError,
    ensure_owned_document_chunks,
)


DEFAULT_RESULT_LIMIT = 5
MAX_RESULT_LIMIT = 12
MAX_QUERY_CHARACTERS = 2_000

BM25_K1 = 1.5
BM25_B = 0.75

TOKEN_PATTERN = re.compile(
    r"[^\W_]+",
    flags=re.UNICODE,
)

PAGE_MARKER_PATTERN = re.compile(
    r"^--- Page\s+\d+\s+---\s*",
    flags=re.MULTILINE,
)


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "do",
    "does",
    "for",
    "from",
    "has",
    "have",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


class DocumentRetrievalError(RuntimeError):
    """Base error for document retrieval."""


class DocumentRetrievalNotFoundError(
    DocumentRetrievalError
):
    """Raised when a document is missing or not owned."""


class DocumentRetrievalNotReadyError(
    DocumentRetrievalError
):
    """Raised when a document cannot be searched."""


class DocumentRetrievalValidationError(
    DocumentRetrievalError
):
    """Raised when the search query is invalid."""


@dataclass(frozen=True)
class RetrievedDocumentChunk:
    """One relevant document chunk."""

    chunk: DocumentChunk
    score: float
    matched_terms: tuple[str, ...]

    @property
    def page_start(self) -> int | None:
        return self.chunk.page_start

    @property
    def page_end(self) -> int | None:
        return self.chunk.page_end

    @property
    def section_title(self) -> str | None:
        return self.chunk.section_title

    @property
    def text(self) -> str:
        return self.chunk.text

    def source(self) -> dict:
        """Create a source compatible with the current UI."""

        if (
            self.page_start
            and self.page_end
            and self.page_start != self.page_end
        ):
            page: int | str | None = (
                f"{self.page_start}-{self.page_end}"
            )
        else:
            page = (
                self.page_start
                or self.page_end
            )

        return {
            "page": page,
            "section": self.section_title,
            "evidence": _evidence_preview(
                self.text
            ),
        }


@dataclass(frozen=True)
class DocumentRetrievalResult:
    """Retrieval result for one document question."""

    document: Document
    query: str
    chunks: list[RetrievedDocumentChunk]
    index_rebuilt: bool


def retrieve_owned_document_chunks(
    *,
    document_id: int,
    user_id: int,
    query: str,
    limit: int = DEFAULT_RESULT_LIMIT,
) -> DocumentRetrievalResult:
    """
    Search an owned document and return its best chunks.

    The chunk index is created or refreshed automatically.
    """

    cleaned_query = _clean_query(
        query
    )

    cleaned_limit = _validate_limit(
        limit
    )

    try:
        indexed_document = ensure_owned_document_chunks(
            document_id=document_id,
            user_id=user_id,
        )

    except DocumentChunkNotFoundError as error:
        raise DocumentRetrievalNotFoundError(
            str(error)
        ) from error

    except DocumentChunkNotReadyError as error:
        raise DocumentRetrievalNotReadyError(
            str(error)
        ) from error

    except DocumentChunkError as error:
        raise DocumentRetrievalError(
            "LifeOS could not prepare the document "
            "for retrieval."
        ) from error

    ranked_chunks = rank_document_chunks(
        query=cleaned_query,
        chunks=indexed_document.chunks,
        limit=cleaned_limit,
    )

    return DocumentRetrievalResult(
        document=indexed_document.document,
        query=cleaned_query,
        chunks=ranked_chunks,
        index_rebuilt=indexed_document.rebuilt,
    )


def rank_document_chunks(
    *,
    query: str,
    chunks: list[DocumentChunk],
    limit: int = DEFAULT_RESULT_LIMIT,
) -> list[RetrievedDocumentChunk]:
    """Rank chunks using BM25 keyword relevance."""

    cleaned_query = _clean_query(
        query
    )

    cleaned_limit = _validate_limit(
        limit
    )

    if not chunks:
        return []

    query_terms = _meaningful_tokens(
        cleaned_query
    )

    if not query_terms:
        return []

    chunk_tokens = [
        _tokenize(chunk.text)
        for chunk in chunks
    ]

    document_count = len(chunks)

    average_chunk_length = (
        sum(
            len(tokens)
            for tokens in chunk_tokens
        )
        / max(document_count, 1)
    )

    document_frequency: Counter[str] = Counter()

    for tokens in chunk_tokens:
        document_frequency.update(
            set(tokens)
        )

    ranked: list[RetrievedDocumentChunk] = []

    for chunk, tokens in zip(
        chunks,
        chunk_tokens,
    ):
        if not tokens:
            continue

        term_frequency = Counter(
            tokens
        )

        score = _calculate_bm25_score(
            query_terms=query_terms,
            term_frequency=term_frequency,
            document_frequency=document_frequency,
            document_count=document_count,
            document_length=len(tokens),
            average_document_length=average_chunk_length,
        )

        section_terms = set(
            _meaningful_tokens(
                chunk.section_title or ""
            )
        )

        section_matches = (
            set(query_terms)
            & section_terms
        )

        score += (
            len(section_matches)
            * 1.2
        )

        matched_terms = tuple(
            sorted(
                {
                    term
                    for term in query_terms
                    if term_frequency.get(
                        term,
                        0,
                    )
                    > 0
                }
            )
        )

        if score <= 0:
            continue

        ranked.append(
            RetrievedDocumentChunk(
                chunk=chunk,
                score=round(
                    score,
                    6,
                ),
                matched_terms=matched_terms,
            )
        )

    ranked.sort(
        key=lambda result: (
            -result.score,
            result.chunk.chunk_index,
        )
    )

    return ranked[:cleaned_limit]


def build_retrieval_context(
    result: DocumentRetrievalResult,
    *,
    max_characters: int = 14_000,
) -> str:
    """Format retrieved chunks for the AI prompt."""

    if max_characters < 500:
        raise ValueError(
            "Retrieval context must allow at least "
            "500 characters."
        )

    blocks: list[str] = []
    used_characters = 0

    for position, retrieved in enumerate(
        result.chunks,
        start=1,
    ):
        label = _source_label(
            retrieved
        )

        clean_text = PAGE_MARKER_PATTERN.sub(
            "",
            retrieved.text,
        ).strip()

        block = (
            f"[Source {position} | {label}]\n"
            f"{clean_text}"
        )

        separator_length = 2 if blocks else 0

        remaining = (
            max_characters
            - used_characters
            - separator_length
        )

        if remaining <= 0:
            break

        if len(block) > remaining:
            if remaining < 200:
                break

            block = (
                block[:remaining - 3].rstrip()
                + "..."
            )

        blocks.append(
            block
        )

        used_characters += (
            len(block)
            + separator_length
        )

    return "\n\n".join(
        blocks
    )


def _calculate_bm25_score(
    *,
    query_terms: list[str],
    term_frequency: Counter[str],
    document_frequency: Counter[str],
    document_count: int,
    document_length: int,
    average_document_length: float,
) -> float:
    """Calculate the BM25 score for one chunk."""

    score = 0.0

    safe_average_length = max(
        average_document_length,
        1.0,
    )

    for term in set(query_terms):
        frequency = term_frequency.get(
            term,
            0,
        )

        if frequency == 0:
            continue

        chunks_containing_term = (
            document_frequency.get(
                term,
                0,
            )
        )

        inverse_document_frequency = math.log(
            1
            + (
                document_count
                - chunks_containing_term
                + 0.5
            )
            / (
                chunks_containing_term
                + 0.5
            )
        )

        length_normalization = (
            1
            - BM25_B
            + BM25_B
            * (
                document_length
                / safe_average_length
            )
        )

        numerator = (
            frequency
            * (
                BM25_K1
                + 1
            )
        )

        denominator = (
            frequency
            + BM25_K1
            * length_normalization
        )

        score += (
            inverse_document_frequency
            * numerator
            / denominator
        )

    return score


def _clean_query(
    query: str,
) -> str:
    cleaned = " ".join(
        str(query or "").split()
    ).strip()

    if not cleaned:
        raise DocumentRetrievalValidationError(
            "Please enter a document question."
        )

    if len(cleaned) > MAX_QUERY_CHARACTERS:
        raise DocumentRetrievalValidationError(
            "The document question cannot exceed "
            f"{MAX_QUERY_CHARACTERS:,} characters."
        )

    return cleaned


def _validate_limit(
    limit: int,
) -> int:
    try:
        cleaned_limit = int(
            limit
        )

    except (TypeError, ValueError) as error:
        raise DocumentRetrievalValidationError(
            "The result limit must be a number."
        ) from error

    if cleaned_limit < 1:
        raise DocumentRetrievalValidationError(
            "The result limit must be at least 1."
        )

    if cleaned_limit > MAX_RESULT_LIMIT:
        raise DocumentRetrievalValidationError(
            "The result limit cannot exceed "
            f"{MAX_RESULT_LIMIT}."
        )

    return cleaned_limit


def _tokenize(
    text: str,
) -> list[str]:
    return [
        token.casefold()
        for token in TOKEN_PATTERN.findall(
            str(text or "")
        )
        if token
    ]


def _meaningful_tokens(
    text: str,
) -> list[str]:
    tokens = _tokenize(
        text
    )

    meaningful = [
        token
        for token in tokens
        if (
            token not in STOP_WORDS
            and len(token) > 1
        )
    ]

    return meaningful or tokens


def _source_label(
    retrieved: RetrievedDocumentChunk,
) -> str:
    labels: list[str] = []

    if (
        retrieved.page_start
        and retrieved.page_end
        and retrieved.page_start != retrieved.page_end
    ):
        labels.append(
            f"Pages {retrieved.page_start}-"
            f"{retrieved.page_end}"
        )

    elif retrieved.page_start:
        labels.append(
            f"Page {retrieved.page_start}"
        )

    elif retrieved.page_end:
        labels.append(
            f"Page {retrieved.page_end}"
        )

    else:
        labels.append(
            "Page unknown"
        )

    if retrieved.section_title:
        labels.append(
            retrieved.section_title
        )

    return " | ".join(
        labels
    )


def _evidence_preview(
    text: str,
    *,
    max_characters: int = 420,
) -> str:
    cleaned = PAGE_MARKER_PATTERN.sub(
        "",
        str(text or ""),
    )

    cleaned = " ".join(
        cleaned.split()
    )

    if len(cleaned) <= max_characters:
        return cleaned

    return (
        cleaned[:max_characters - 3].rstrip()
        + "..."
    )
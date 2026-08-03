"""Hybrid keyword and semantic retrieval for Document Brain."""

from __future__ import annotations

import re
from dataclasses import dataclass

from models import (
    Document,
    DocumentChunk,
)
from services.document_retrieval_service import (
    DocumentRetrievalError,
    DocumentRetrievalNotFoundError,
    DocumentRetrievalNotReadyError,
    DocumentRetrievalValidationError,
    RetrievedDocumentChunk,
    retrieve_owned_document_chunks,
)
from services.document_semantic_retrieval_service import (
    DocumentSemanticRetrievalError,
    DocumentSemanticRetrievalNotFoundError,
    DocumentSemanticRetrievalNotReadyError,
    DocumentSemanticRetrievalValidationError,
    SemanticRetrievedDocumentChunk,
    retrieve_owned_document_chunks_semantically,
)


DEFAULT_RESULT_LIMIT = 5
MAX_RESULT_LIMIT = 12
DEFAULT_CANDIDATE_LIMIT = 12
MAX_QUERY_CHARACTERS = 2_000

DEFAULT_KEYWORD_WEIGHT = 0.5
DEFAULT_SEMANTIC_WEIGHT = 0.5
RRF_CONSTANT = 60.0

PAGE_MARKER_PATTERN = re.compile(
    r"^--- Page\s+\d+\s+---\s*",
    flags=re.MULTILINE,
)


class DocumentHybridRetrievalError(RuntimeError):
    """Base error for hybrid document retrieval."""


class DocumentHybridRetrievalNotFoundError(
    DocumentHybridRetrievalError
):
    """Raised when a document is missing or not owned."""


class DocumentHybridRetrievalNotReadyError(
    DocumentHybridRetrievalError
):
    """Raised when a document cannot be searched."""


class DocumentHybridRetrievalValidationError(
    DocumentHybridRetrievalError
):
    """Raised when hybrid-retrieval input is invalid."""


@dataclass(frozen=True)
class HybridRetrievedDocumentChunk:
    """One chunk ranked using keyword and semantic retrieval."""

    chunk: DocumentChunk
    score: float

    keyword_score: float | None
    semantic_score: float | None

    keyword_rank: int | None
    semantic_rank: int | None

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

    @property
    def retrieval_methods(self) -> tuple[str, ...]:
        """Return the retrieval methods that found this chunk."""

        methods: list[str] = []

        if self.keyword_rank is not None:
            methods.append("keyword")

        if self.semantic_rank is not None:
            methods.append("semantic")

        return tuple(methods)

    def source(self) -> dict:
        """Return a source compatible with Document Brain."""

        if (
            self.page_start
            and self.page_end
            and self.page_start != self.page_end
        ):
            page: int | str | None = (
                f"{self.page_start}-"
                f"{self.page_end}"
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
class DocumentHybridRetrievalResult:
    """Combined retrieval result for one document question."""

    document: Document
    query: str

    chunks: list[
        HybridRetrievedDocumentChunk
    ]

    mode: str

    keyword_result_count: int
    semantic_result_count: int

    index_rebuilt: bool
    chunks_rebuilt: bool

    embedded_count: int
    reused_count: int

    embedding_provider: str | None
    embedding_model: str | None
    embedding_dimensions: int | None

    semantic_error: str | None


@dataclass
class _FusionCandidate:
    """Mutable candidate used while combining rankings."""

    chunk: DocumentChunk
    score: float = 0.0

    keyword_score: float | None = None
    semantic_score: float | None = None

    keyword_rank: int | None = None
    semantic_rank: int | None = None

    matched_terms: tuple[str, ...] = ()


def retrieve_owned_document_chunks_hybrid(
    *,
    document_id: int,
    user_id: int,
    query: str,
    limit: int = DEFAULT_RESULT_LIMIT,
    keyword_weight: float = DEFAULT_KEYWORD_WEIGHT,
    semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT,
    force_embeddings: bool = False,
) -> DocumentHybridRetrievalResult:
    """
    Retrieve chunks using BM25 and semantic vector search.

    Semantic retrieval may fall back to keyword retrieval when the
    embedding provider is temporarily unavailable.
    """

    cleaned_query = _clean_query(
        query
    )

    cleaned_limit = _validate_limit(
        limit
    )

    (
        cleaned_keyword_weight,
        cleaned_semantic_weight,
    ) = _validate_weights(
        keyword_weight=keyword_weight,
        semantic_weight=semantic_weight,
    )

    candidate_limit = min(
        MAX_RESULT_LIMIT,
        max(
            DEFAULT_CANDIDATE_LIMIT,
            cleaned_limit,
        ),
    )

    try:
        keyword_result = retrieve_owned_document_chunks(
            document_id=document_id,
            user_id=user_id,
            query=cleaned_query,
            limit=candidate_limit,
        )

    except DocumentRetrievalNotFoundError as error:
        raise DocumentHybridRetrievalNotFoundError(
            str(error)
        ) from error

    except DocumentRetrievalNotReadyError as error:
        raise DocumentHybridRetrievalNotReadyError(
            str(error)
        ) from error

    except DocumentRetrievalValidationError as error:
        raise DocumentHybridRetrievalValidationError(
            str(error)
        ) from error

    except DocumentRetrievalError as error:
        raise DocumentHybridRetrievalError(
            str(error)
        ) from error

    semantic_result = None
    semantic_error: str | None = None

    try:
        semantic_result = (
            retrieve_owned_document_chunks_semantically(
                document_id=document_id,
                user_id=user_id,
                query=cleaned_query,
                limit=candidate_limit,
                force_embeddings=force_embeddings,
            )
        )

    except DocumentSemanticRetrievalNotFoundError as error:
        raise DocumentHybridRetrievalNotFoundError(
            str(error)
        ) from error

    except DocumentSemanticRetrievalNotReadyError as error:
        raise DocumentHybridRetrievalNotReadyError(
            str(error)
        ) from error

    except DocumentSemanticRetrievalValidationError as error:
        raise DocumentHybridRetrievalValidationError(
            str(error)
        ) from error

    except DocumentSemanticRetrievalError as error:
        semantic_error = str(error)

        # Keep Document Brain available during an embedding
        # provider outage when BM25 found usable evidence.
        if not keyword_result.chunks:
            raise DocumentHybridRetrievalError(
                str(error)
            ) from error

    semantic_chunks = (
        semantic_result.chunks
        if semantic_result is not None
        else []
    )

    fused_chunks = fuse_retrieval_results(
        keyword_chunks=keyword_result.chunks,
        semantic_chunks=semantic_chunks,
        limit=cleaned_limit,
        keyword_weight=cleaned_keyword_weight,
        semantic_weight=cleaned_semantic_weight,
    )

    mode = _retrieval_mode(
        keyword_count=len(
            keyword_result.chunks
        ),
        semantic_count=len(
            semantic_chunks
        ),
        semantic_error=semantic_error,
    )

    return DocumentHybridRetrievalResult(
        document=keyword_result.document,
        query=cleaned_query,
        chunks=fused_chunks,
        mode=mode,
        keyword_result_count=len(
            keyword_result.chunks
        ),
        semantic_result_count=len(
            semantic_chunks
        ),
        index_rebuilt=keyword_result.index_rebuilt,
        chunks_rebuilt=(
            semantic_result.chunks_rebuilt
            if semantic_result is not None
            else False
        ),
        embedded_count=(
            semantic_result.embedded_count
            if semantic_result is not None
            else 0
        ),
        reused_count=(
            semantic_result.reused_count
            if semantic_result is not None
            else 0
        ),
        embedding_provider=(
            semantic_result.provider
            if semantic_result is not None
            else None
        ),
        embedding_model=(
            semantic_result.model
            if semantic_result is not None
            else None
        ),
        embedding_dimensions=(
            semantic_result.dimensions
            if semantic_result is not None
            else None
        ),
        semantic_error=semantic_error,
    )


def fuse_retrieval_results(
    *,
    keyword_chunks: list[
        RetrievedDocumentChunk
    ],
    semantic_chunks: list[
        SemanticRetrievedDocumentChunk
    ],
    limit: int = DEFAULT_RESULT_LIMIT,
    keyword_weight: float = DEFAULT_KEYWORD_WEIGHT,
    semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT,
) -> list[HybridRetrievedDocumentChunk]:
    """
    Combine BM25 and semantic rankings using weighted RRF.

    A chunk appearing near the top of both rankings receives the
    strongest combined score.
    """

    cleaned_limit = _validate_limit(
        limit
    )

    (
        cleaned_keyword_weight,
        cleaned_semantic_weight,
    ) = _validate_weights(
        keyword_weight=keyword_weight,
        semantic_weight=semantic_weight,
    )

    candidates: dict[
        tuple[int | None, int],
        _FusionCandidate,
    ] = {}

    for rank, retrieved in enumerate(
        keyword_chunks,
        start=1,
    ):
        key = _chunk_key(
            retrieved.chunk
        )

        candidate = candidates.setdefault(
            key,
            _FusionCandidate(
                chunk=retrieved.chunk
            ),
        )

        candidate.keyword_rank = rank
        candidate.keyword_score = (
            retrieved.score
        )
        candidate.matched_terms = (
            retrieved.matched_terms
        )

        candidate.score += (
            cleaned_keyword_weight
            / (
                RRF_CONSTANT
                + rank
            )
        )

    for rank, retrieved in enumerate(
        semantic_chunks,
        start=1,
    ):
        key = _chunk_key(
            retrieved.chunk
        )

        candidate = candidates.setdefault(
            key,
            _FusionCandidate(
                chunk=retrieved.chunk
            ),
        )

        candidate.semantic_rank = rank
        candidate.semantic_score = (
            retrieved.score
        )

        candidate.score += (
            cleaned_semantic_weight
            / (
                RRF_CONSTANT
                + rank
            )
        )

    ranked = [
        HybridRetrievedDocumentChunk(
            chunk=candidate.chunk,
            score=round(
                candidate.score,
                10,
            ),
            keyword_score=(
                candidate.keyword_score
            ),
            semantic_score=(
                candidate.semantic_score
            ),
            keyword_rank=(
                candidate.keyword_rank
            ),
            semantic_rank=(
                candidate.semantic_rank
            ),
            matched_terms=(
                candidate.matched_terms
            ),
        )
        for candidate in candidates.values()
    ]

    ranked.sort(
        key=lambda result: (
            -result.score,
            _best_rank(result),
            result.chunk.chunk_index,
        )
    )

    return ranked[
        :cleaned_limit
    ]


def build_hybrid_retrieval_context(
    result: DocumentHybridRetrievalResult,
    *,
    max_characters: int = 14_000,
) -> str:
    """Format hybrid-retrieved chunks for the AI prompt."""

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

        separator_length = (
            2 if blocks else 0
        )

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
                block[
                    :remaining - 3
                ].rstrip()
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


def _chunk_key(
    chunk: DocumentChunk,
) -> tuple[int | None, int]:
    """Return a stable key for one document chunk."""

    return (
        chunk.document_id,
        chunk.chunk_index,
    )


def _best_rank(
    result: HybridRetrievedDocumentChunk,
) -> int:
    ranks = [
        rank
        for rank in (
            result.keyword_rank,
            result.semantic_rank,
        )
        if rank is not None
    ]

    return min(
        ranks,
        default=MAX_RESULT_LIMIT + 1,
    )


def _retrieval_mode(
    *,
    keyword_count: int,
    semantic_count: int,
    semantic_error: str | None,
) -> str:
    if semantic_error:
        return "keyword_fallback"

    if keyword_count and semantic_count:
        return "hybrid"

    if semantic_count:
        return "semantic_only"

    return "keyword_only"


def _clean_query(
    query: str,
) -> str:
    cleaned = " ".join(
        str(query or "").split()
    ).strip()

    if not cleaned:
        raise DocumentHybridRetrievalValidationError(
            "Please enter a document question."
        )

    if len(cleaned) > MAX_QUERY_CHARACTERS:
        raise DocumentHybridRetrievalValidationError(
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

    except (
        TypeError,
        ValueError,
    ) as error:
        raise DocumentHybridRetrievalValidationError(
            "The result limit must be a number."
        ) from error

    if cleaned_limit < 1:
        raise DocumentHybridRetrievalValidationError(
            "The result limit must be at least 1."
        )

    if cleaned_limit > MAX_RESULT_LIMIT:
        raise DocumentHybridRetrievalValidationError(
            "The result limit cannot exceed "
            f"{MAX_RESULT_LIMIT}."
        )

    return cleaned_limit


def _validate_weights(
    *,
    keyword_weight: float,
    semantic_weight: float,
) -> tuple[float, float]:
    try:
        cleaned_keyword_weight = float(
            keyword_weight
        )

        cleaned_semantic_weight = float(
            semantic_weight
        )

    except (
        TypeError,
        ValueError,
    ) as error:
        raise DocumentHybridRetrievalValidationError(
            "Retrieval weights must be numbers."
        ) from error

    if (
        cleaned_keyword_weight < 0
        or cleaned_semantic_weight < 0
    ):
        raise DocumentHybridRetrievalValidationError(
            "Retrieval weights cannot be negative."
        )

    total_weight = (
        cleaned_keyword_weight
        + cleaned_semantic_weight
    )

    if total_weight == 0:
        raise DocumentHybridRetrievalValidationError(
            "At least one retrieval weight must be greater "
            "than zero."
        )

    # Normalize the weights so callers may use values such
    # as 50/50 or 0.5/0.5.
    return (
        cleaned_keyword_weight
        / total_weight,
        cleaned_semantic_weight
        / total_weight,
    )


def _source_label(
    retrieved: HybridRetrievedDocumentChunk,
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
        cleaned[
            :max_characters - 3
        ].rstrip()
        + "..."
    )
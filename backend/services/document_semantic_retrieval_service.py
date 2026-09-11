"""Semantic vector retrieval for LifeOS Document Brain."""

from __future__ import annotations

import re
from dataclasses import dataclass

from models import (
    Document,
    DocumentChunk,
)
from services.document_embedding_service import (
    DocumentEmbeddingError,
    DocumentEmbeddingNotFoundError,
    DocumentEmbeddingNotReadyError,
    cosine_similarity,
    ensure_owned_document_embeddings,
    generate_question_embedding,
)


DEFAULT_RESULT_LIMIT = 5
MAX_RESULT_LIMIT = 12
MAX_QUERY_CHARACTERS = 2_000

PAGE_MARKER_PATTERN = re.compile(
    r"^--- Page\s+\d+\s+---\s*",
    flags=re.MULTILINE,
)


class DocumentSemanticRetrievalError(
    RuntimeError
):
    """Base semantic-retrieval error."""


class DocumentSemanticRetrievalNotFoundError(
    DocumentSemanticRetrievalError
):
    """Raised when a document is missing or not owned."""


class DocumentSemanticRetrievalNotReadyError(
    DocumentSemanticRetrievalError
):
    """Raised when a document cannot be searched."""


class DocumentSemanticRetrievalValidationError(
    DocumentSemanticRetrievalError
):
    """Raised when semantic-search input is invalid."""


@dataclass(frozen=True)
class SemanticRetrievedDocumentChunk:
    """One chunk ranked using vector similarity."""

    chunk: DocumentChunk
    score: float

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
class DocumentSemanticRetrievalResult:
    """Semantic retrieval result for one question."""

    document: Document
    query: str
    chunks: list[
        SemanticRetrievedDocumentChunk
    ]

    embedded_count: int
    reused_count: int
    chunks_rebuilt: bool

    provider: str
    model: str
    dimensions: int


def retrieve_owned_document_chunks_semantically(
    *,
    document_id: int,
    user_id: int,
    query: str,
    limit: int = DEFAULT_RESULT_LIMIT,
    force_embeddings: bool = False,
) -> DocumentSemanticRetrievalResult:
    """
    Retrieve chunks according to semantic similarity.

    The document chunks and embeddings are created or refreshed
    automatically before retrieval.
    """

    cleaned_query = _clean_query(
        query
    )

    cleaned_limit = _validate_limit(
        limit
    )

    try:
        embedded_document = (
            ensure_owned_document_embeddings(
                document_id=document_id,
                user_id=user_id,
                force=force_embeddings,
            )
        )

    except DocumentEmbeddingNotFoundError as error:
        raise (
            DocumentSemanticRetrievalNotFoundError(
                str(error)
            )
        ) from error

    except DocumentEmbeddingNotReadyError as error:
        raise (
            DocumentSemanticRetrievalNotReadyError(
                str(error)
            )
        ) from error

    except DocumentEmbeddingError as error:
        raise DocumentSemanticRetrievalError(
            str(error)
        ) from error

    try:
        (
            question_embedding,
            question_configuration,
        ) = generate_question_embedding(
            question=cleaned_query
        )

    except DocumentEmbeddingError as error:
        raise DocumentSemanticRetrievalError(
            str(error)
        ) from error

    if (
        question_configuration.provider
        != embedded_document.provider
        or question_configuration.model
        != embedded_document.model
        or question_configuration.dimensions
        != embedded_document.dimensions
    ):
        raise DocumentSemanticRetrievalError(
            "The question and document embeddings use "
            "different configurations."
        )

    ranked_chunks = rank_semantic_document_chunks(
        question_embedding=question_embedding,
        chunks=embedded_document.chunks,
        limit=cleaned_limit,
    )

    return DocumentSemanticRetrievalResult(
        document=embedded_document.document,
        query=cleaned_query,
        chunks=ranked_chunks,
        embedded_count=(
            embedded_document.embedded_count
        ),
        reused_count=(
            embedded_document.reused_count
        ),
        chunks_rebuilt=(
            embedded_document.chunks_rebuilt
        ),
        provider=embedded_document.provider,
        model=embedded_document.model,
        dimensions=embedded_document.dimensions,
    )


def rank_semantic_document_chunks(
    *,
    question_embedding: list[float],
    chunks: list[DocumentChunk],
    limit: int = DEFAULT_RESULT_LIMIT,
) -> list[
    SemanticRetrievedDocumentChunk
]:
    """Rank stored chunks using cosine similarity."""

    cleaned_limit = _validate_limit(
        limit
    )

    if not question_embedding:
        raise DocumentSemanticRetrievalValidationError(
            "The question embedding cannot be empty."
        )

    ranked_chunks: list[
        SemanticRetrievedDocumentChunk
    ] = []

    for chunk in chunks:
        chunk_embedding = chunk.embedding

        if not chunk_embedding:
            continue

        if (
            len(chunk_embedding)
            != len(question_embedding)
        ):
            continue

        similarity = cosine_similarity(
            question_embedding,
            chunk_embedding,
        )

        ranked_chunks.append(
            SemanticRetrievedDocumentChunk(
                chunk=chunk,
                score=round(
                    similarity,
                    8,
                ),
            )
        )

    ranked_chunks.sort(
        key=lambda result: (
            -result.score,
            result.chunk.chunk_index,
        )
    )

    return ranked_chunks[
        :cleaned_limit
    ]


def _clean_query(
    query: str,
) -> str:
    cleaned = " ".join(
        str(query or "").split()
    ).strip()

    if not cleaned:
        raise (
            DocumentSemanticRetrievalValidationError(
                "Please enter a document question."
            )
        )

    if len(cleaned) > MAX_QUERY_CHARACTERS:
        raise (
            DocumentSemanticRetrievalValidationError(
                "The document question cannot exceed "
                f"{MAX_QUERY_CHARACTERS:,} characters."
            )
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
        raise (
            DocumentSemanticRetrievalValidationError(
                "The result limit must be a number."
            )
        ) from error

    if cleaned_limit < 1:
        raise (
            DocumentSemanticRetrievalValidationError(
                "The result limit must be at least 1."
            )
        )

    if cleaned_limit > MAX_RESULT_LIMIT:
        raise (
            DocumentSemanticRetrievalValidationError(
                "The result limit cannot exceed "
                f"{MAX_RESULT_LIMIT}."
            )
        )

    return cleaned_limit


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
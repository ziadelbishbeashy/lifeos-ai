"""Hybrid retrieval across user-defined document collections (Step 17)."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from services.resource_limit_service import (
    ResourceLimitError,
    effective_context_limit,
    enforce_scope_document_count,
    get_resource_limits,
)
from models import Document, DocumentCollection, DocumentCollectionItem, Project
from services.document_chunk_service import (
    DocumentChunkError,
    DocumentChunkNotFoundError,
    DocumentChunkNotReadyError,
    ensure_owned_document_chunks,
)
from services.document_embedding_service import (
    DocumentEmbeddingError,
    DocumentEmbeddingNotFoundError,
    DocumentEmbeddingNotReadyError,
    ensure_owned_document_embeddings,
    generate_question_embedding,
)
from services.document_hybrid_retrieval_service import (
    HybridRetrievedDocumentChunk,
    fuse_retrieval_results,
)
from services.document_retrieval_service import (
    MAX_RESULT_LIMIT as KEYWORD_MAX_RESULT_LIMIT,
    DocumentRetrievalValidationError,
    rank_document_chunks,
)
from services.document_semantic_retrieval_service import (
    MAX_RESULT_LIMIT as SEMANTIC_MAX_RESULT_LIMIT,
    DocumentSemanticRetrievalValidationError,
    rank_semantic_document_chunks,
)
from services.document_version_service import current_document_filter


DEFAULT_RESULT_LIMIT = 10
MAX_RESULT_LIMIT = 12
# Collection retrieval must stay inside the limits enforced by the authoritative
# keyword and semantic rankers. The previous value (14) exceeded both services'
# MAX_RESULT_LIMIT=12 and could raise an uncaught validation exception after the
# SQL Server boolean-filter issue was fixed.
GLOBAL_CANDIDATE_LIMIT = min(
    KEYWORD_MAX_RESULT_LIMIT,
    SEMANTIC_MAX_RESULT_LIMIT,
    MAX_RESULT_LIMIT,
)
MAX_QUERY_CHARACTERS = 2_000
RETRIEVAL_CONTEXT_CHARACTERS = 18_000

PAGE_MARKER_PATTERN = re.compile(
    r"^--- Page\s+\d+\s+---\s*",
    flags=re.MULTILINE,
)


class CollectionRetrievalError(RuntimeError):
    pass


class CollectionRetrievalNotFoundError(CollectionRetrievalError):
    pass


class CollectionRetrievalNotReadyError(CollectionRetrievalError):
    pass


class CollectionRetrievalValidationError(CollectionRetrievalError):
    pass


@dataclass(frozen=True)
class CollectionRetrievedChunk:
    document: Document
    retrieved: HybridRetrievedDocumentChunk

    @property
    def chunk(self):
        return self.retrieved.chunk

    @property
    def matched_terms(self):
        return self.retrieved.matched_terms

    @property
    def page_start(self):
        return self.retrieved.page_start

    @property
    def page_end(self):
        return self.retrieved.page_end

    @property
    def section_title(self):
        return self.retrieved.section_title

    @property
    def text(self):
        return self.retrieved.text

    def source(self) -> dict[str, Any]:
        base = self.retrieved.source()
        return {
            "document_id": self.document.id,
            "filename": self.document.filename,
            "page": base.get("page"),
            "section": base.get("section"),
            "evidence": base.get("evidence"),
            "chunk_id": self.chunk.id,
            "chunk_index": self.chunk.chunk_index,
            "content_type": getattr(self.chunk, "content_type", "text") or "text",
            "table_id": getattr(self.chunk, "table_id", None),
            "visibility": "collection_owner",
        }


@dataclass(frozen=True)
class CollectionRetrievalResult:
    collection: DocumentCollection
    query: str
    chunks: list[CollectionRetrievedChunk]
    document_count: int
    searchable_document_count: int
    skipped_document_count: int
    mode: str
    semantic_error: str | None
    chunks_rebuilt_count: int
    embedded_count: int
    reused_count: int


def retrieve_owned_collection_chunks(
    *,
    collection_id: int,
    user_id: int,
    query: str,
    limit: int = DEFAULT_RESULT_LIMIT,
    force_embeddings: bool = False,
) -> CollectionRetrievalResult:
    """Search all current, owned documents in one collection with the existing RAG rankers."""

    cleaned_query = _clean_query(query)
    cleaned_limit = _validate_limit(limit)

    collection = DocumentCollection.query.filter_by(
        id=collection_id,
        user_id=user_id,
    ).first()
    if collection is None:
        raise CollectionRetrievalNotFoundError("Collection not found.")

    # Defense in depth: collection membership is ownership-checked at mutation
    # time, and retrieval independently joins Project so a malformed row can
    # never expose another user's document. Historical versions are excluded by
    # the one shared current_document_filter().
    documents = (
        Document.query
        .join(
            DocumentCollectionItem,
            DocumentCollectionItem.document_id == Document.id,
        )
        .filter(
            DocumentCollectionItem.collection_id == collection.id,
            Document.user_id == user_id,
            current_document_filter(),
        )
        .order_by(Document.uploaded_at.desc(), Document.id.desc())
        .all()
    )

    if not documents:
        raise CollectionRetrievalNotReadyError(
            "This collection does not contain any current documents yet."
        )
    try:
        enforce_scope_document_count(len(documents), scope_label="collection")
    except ResourceLimitError as error:
        raise CollectionRetrievalValidationError(str(error)) from error

    searchable_documents: list[Document] = []
    all_chunks = []
    documents_by_id: dict[int, Document] = {}
    skipped_count = 0
    rebuilt_count = 0

    for document in documents:
        try:
            indexed = ensure_owned_document_chunks(
                document_id=document.id,
                user_id=user_id,
            )
        except (DocumentChunkNotReadyError, DocumentChunkNotFoundError):
            skipped_count += 1
            continue
        except DocumentChunkError as error:
            raise CollectionRetrievalError(
                "LifeOS could not prepare collection documents for search."
            ) from error

        searchable_documents.append(indexed.document)
        documents_by_id[indexed.document.id] = indexed.document
        all_chunks.extend(indexed.chunks)
        rebuilt_count += int(bool(indexed.rebuilt))

    if not searchable_documents or not all_chunks:
        raise CollectionRetrievalNotReadyError(
            "None of the collection documents contains searchable text or structured tables yet."
        )

    try:
        keyword_chunks = rank_document_chunks(
            query=cleaned_query,
            chunks=all_chunks,
            limit=GLOBAL_CANDIDATE_LIMIT,
        )
    except DocumentRetrievalValidationError as error:
        raise CollectionRetrievalValidationError(str(error)) from error

    semantic_chunks = []
    semantic_error: str | None = None
    embedded_count = 0
    reused_count = 0

    try:
        embedded_chunks = []
        expected_configuration: tuple[str, str, int] | None = None

        for document in searchable_documents:
            embedded = ensure_owned_document_embeddings(
                document_id=document.id,
                user_id=user_id,
                force=force_embeddings,
            )
            configuration = (
                embedded.provider,
                embedded.model,
                embedded.dimensions,
            )

            if expected_configuration is None:
                expected_configuration = configuration
            elif configuration != expected_configuration:
                raise DocumentEmbeddingError(
                    "Collection document embeddings use inconsistent configurations."
                )

            embedded_chunks.extend(embedded.chunks)
            embedded_count += embedded.embedded_count
            reused_count += embedded.reused_count
            rebuilt_count += int(bool(embedded.chunks_rebuilt))

        question_embedding, question_configuration = generate_question_embedding(
            question=cleaned_query
        )
        question_identity = (
            question_configuration.provider,
            question_configuration.model,
            question_configuration.dimensions,
        )

        if (
            expected_configuration is not None
            and question_identity != expected_configuration
        ):
            raise DocumentEmbeddingError(
                "The question and collection document embeddings use different configurations."
            )

        try:
            semantic_chunks = rank_semantic_document_chunks(
                question_embedding=question_embedding,
                chunks=embedded_chunks,
                limit=GLOBAL_CANDIDATE_LIMIT,
            )
        except DocumentSemanticRetrievalValidationError as error:
            raise CollectionRetrievalValidationError(str(error)) from error

    except CollectionRetrievalValidationError:
        raise
    except (
        DocumentEmbeddingNotFoundError,
        DocumentEmbeddingNotReadyError,
        DocumentEmbeddingError,
    ) as error:
        # Preserve the existing keyword fallback. Grounding is still enforced by
        # the answerability verifier before answer generation.
        semantic_chunks = []
        semantic_error = str(error)

    fused_chunks = fuse_retrieval_results(
        keyword_chunks=keyword_chunks,
        semantic_chunks=semantic_chunks,
        limit=cleaned_limit,
    )

    wrapped_chunks = [
        CollectionRetrievedChunk(
            document=documents_by_id[item.chunk.document_id],
            retrieved=item,
        )
        for item in fused_chunks
        if item.chunk.document_id in documents_by_id
    ]

    return CollectionRetrievalResult(
        collection=collection,
        query=cleaned_query,
        chunks=wrapped_chunks,
        document_count=len(documents),
        searchable_document_count=len(searchable_documents),
        skipped_document_count=skipped_count,
        mode=_mode(
            keyword_count=len(keyword_chunks),
            semantic_count=len(semantic_chunks),
            semantic_error=semantic_error,
        ),
        semantic_error=semantic_error,
        chunks_rebuilt_count=rebuilt_count,
        embedded_count=embedded_count,
        reused_count=reused_count,
    )


def select_collection_sources(
    *,
    retrieval_result: CollectionRetrievalResult,
    source_ids,
) -> CollectionRetrievalResult:
    selected = []
    seen: set[int] = set()

    for raw_source_id in source_ids:
        try:
            source_id = int(raw_source_id)
        except (TypeError, ValueError):
            continue

        if (
            source_id in seen
            or source_id < 1
            or source_id > len(retrieval_result.chunks)
        ):
            continue

        seen.add(source_id)
        selected.append(retrieval_result.chunks[source_id - 1])

    if not selected:
        raise CollectionRetrievalValidationError(
            "The verifier did not select a valid collection source."
        )

    return replace(retrieval_result, chunks=selected)


def build_collection_context(
    result: CollectionRetrievalResult,
    *,
    max_characters: int = RETRIEVAL_CONTEXT_CHARACTERS,
) -> str:
    if max_characters < 500:
        raise ValueError(
            "Collection retrieval context must allow at least 500 characters."
        )
    max_characters = effective_context_limit(max_characters)

    blocks: list[str] = []
    used_characters = 0

    for source_id, retrieved in enumerate(result.chunks, start=1):
        labels = [f'Document "{_clean_label(retrieved.document.filename, 220)}"']
        page = _page_label(retrieved)
        if page:
            labels.append(f"Page {page}")

        section = _clean_label(retrieved.section_title, 220)
        if section:
            labels.append(section)

        if (getattr(retrieved.chunk, "content_type", "text") or "text") == "table":
            labels.append("Structured table")

        clean_text = PAGE_MARKER_PATTERN.sub(
            "",
            str(retrieved.text or ""),
        ).strip()
        block = f"[Source {source_id} | {' | '.join(labels)}]\n{clean_text}"

        separator_length = 2 if blocks else 0
        remaining = max_characters - used_characters - separator_length
        if remaining <= 0:
            break

        if len(block) > remaining:
            if remaining < 200:
                break
            block = block[: remaining - 3].rstrip() + "..."

        blocks.append(block)
        used_characters += len(block) + separator_length

    return "\n\n".join(blocks)


def _page_label(retrieved: CollectionRetrievedChunk) -> str:
    if (
        retrieved.page_start
        and retrieved.page_end
        and retrieved.page_start != retrieved.page_end
    ):
        return f"{retrieved.page_start}-{retrieved.page_end}"

    page = retrieved.page_start or retrieved.page_end
    return str(page) if page else ""


def _mode(*, keyword_count: int, semantic_count: int, semantic_error: str | None) -> str:
    if semantic_error:
        return "keyword_fallback"
    if keyword_count and semantic_count:
        return "hybrid"
    if semantic_count:
        return "semantic_only"
    return "keyword_only"


def _clean_query(query: str) -> str:
    cleaned = " ".join(str(query or "").split()).strip()
    if not cleaned:
        raise CollectionRetrievalValidationError(
            "Please enter a collection question."
        )
    if len(cleaned) > MAX_QUERY_CHARACTERS:
        raise CollectionRetrievalValidationError(
            "The collection question cannot exceed "
            f"{MAX_QUERY_CHARACTERS:,} characters."
        )
    return cleaned


def _validate_limit(value) -> int:
    try:
        cleaned = int(value)
    except (TypeError, ValueError) as error:
        raise CollectionRetrievalValidationError(
            "The result limit must be a number."
        ) from error

    max_allowed = min(MAX_RESULT_LIMIT, get_resource_limits().max_retrieval_results)
    if cleaned < 1 or cleaned > max_allowed:
        raise CollectionRetrievalValidationError(
            f"The result limit must be between 1 and {max_allowed}."
        )
    return cleaned


def _clean_label(value, max_length: int) -> str:
    return " ".join(str(value or "").split()).strip()[:max_length]

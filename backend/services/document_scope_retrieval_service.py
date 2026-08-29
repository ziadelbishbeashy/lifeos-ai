"""Shared hybrid retrieval across an explicit owned set of current documents.

This is the scope adapter used by workspaces that are neither a single Document
nor a Project. It does not create another RAG implementation: chunking,
embeddings, keyword ranking, semantic ranking, hybrid fusion, and grounding all
remain the existing authoritative Document Brain services.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Iterable

from services.resource_limit_service import (
    ResourceLimitError,
    effective_context_limit,
    enforce_scope_document_count,
    get_resource_limits,
)
from models import Document, DocumentChunk
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

DEFAULT_RESULT_LIMIT = 10
MAX_RESULT_LIMIT = 12
GLOBAL_CANDIDATE_LIMIT = min(
    KEYWORD_MAX_RESULT_LIMIT,
    SEMANTIC_MAX_RESULT_LIMIT,
    MAX_RESULT_LIMIT,
)
MAX_QUERY_CHARACTERS = 2_000
RETRIEVAL_CONTEXT_CHARACTERS = 18_000
PAGE_MARKER_PATTERN = re.compile(r"^--- Page\s+\d+\s+---\s*", flags=re.MULTILINE)


class DocumentScopeRetrievalError(RuntimeError):
    pass


class DocumentScopeRetrievalNotReadyError(DocumentScopeRetrievalError):
    pass


class DocumentScopeRetrievalValidationError(DocumentScopeRetrievalError, ValueError):
    pass


@dataclass(frozen=True)
class ScopeRetrievedChunk:
    document: Document
    retrieved: HybridRetrievedDocumentChunk
    visibility: str = "workspace_owner"

    @property
    def chunk(self) -> DocumentChunk:
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
            "visibility": self.visibility,
        }


@dataclass(frozen=True)
class DocumentScopeRetrievalResult:
    query: str
    chunks: list[ScopeRetrievedChunk]
    document_count: int
    searchable_document_count: int
    skipped_document_count: int
    mode: str
    semantic_error: str | None
    chunks_rebuilt_count: int
    embedded_count: int
    reused_count: int


def retrieve_owned_document_set(
    *,
    documents: Iterable[Document],
    user_id: int,
    query: str,
    limit: int = DEFAULT_RESULT_LIMIT,
    force_embeddings: bool = False,
    visibility: str = "workspace_owner",
) -> DocumentScopeRetrievalResult:
    """Search an already-scoped set through the existing Document Brain stack."""

    cleaned_query = _clean_query(query)
    cleaned_limit = _validate_limit(limit)

    unique_documents: list[Document] = []
    seen: set[int] = set()
    for document in documents:
        if document is None or document.id in seen:
            continue
        if int(getattr(document, "user_id", 0) or 0) != int(user_id):
            raise DocumentScopeRetrievalValidationError(
                "A document in this workspace is not owned by the current user."
            )
        if not bool(getattr(document, "is_current_version", True)):
            continue
        seen.add(document.id)
        unique_documents.append(document)

    if not unique_documents:
        raise DocumentScopeRetrievalNotReadyError(
            "This workspace does not contain any current documents yet."
        )
    try:
        enforce_scope_document_count(len(unique_documents), scope_label="workspace")
    except ResourceLimitError as error:
        raise DocumentScopeRetrievalValidationError(str(error)) from error

    searchable_documents: list[Document] = []
    all_chunks: list[DocumentChunk] = []
    documents_by_id: dict[int, Document] = {}
    skipped_count = 0
    rebuilt_count = 0

    for document in unique_documents:
        try:
            indexed = ensure_owned_document_chunks(
                document_id=document.id,
                user_id=user_id,
            )
        except (DocumentChunkNotReadyError, DocumentChunkNotFoundError):
            skipped_count += 1
            continue
        except DocumentChunkError as error:
            raise DocumentScopeRetrievalError(
                "LifeOS could not prepare workspace documents for search."
            ) from error

        if not indexed.chunks:
            skipped_count += 1
            continue

        searchable_documents.append(indexed.document)
        documents_by_id[indexed.document.id] = indexed.document
        all_chunks.extend(indexed.chunks)
        rebuilt_count += int(bool(indexed.rebuilt))

    if not searchable_documents or not all_chunks:
        raise DocumentScopeRetrievalNotReadyError(
            "None of the workspace documents contains searchable text or structured tables yet."
        )

    try:
        keyword_chunks = rank_document_chunks(
            query=cleaned_query,
            chunks=all_chunks,
            limit=GLOBAL_CANDIDATE_LIMIT,
        )
    except DocumentRetrievalValidationError as error:
        raise DocumentScopeRetrievalValidationError(str(error)) from error

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
            configuration = (embedded.provider, embedded.model, embedded.dimensions)
            if expected_configuration is None:
                expected_configuration = configuration
            elif configuration != expected_configuration:
                raise DocumentEmbeddingError(
                    "Workspace document embeddings use inconsistent configurations."
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
        if expected_configuration is not None and question_identity != expected_configuration:
            raise DocumentEmbeddingError(
                "The question and workspace document embeddings use different configurations."
            )

        try:
            semantic_chunks = rank_semantic_document_chunks(
                question_embedding=question_embedding,
                chunks=embedded_chunks,
                limit=GLOBAL_CANDIDATE_LIMIT,
            )
        except DocumentSemanticRetrievalValidationError as error:
            raise DocumentScopeRetrievalValidationError(str(error)) from error

    except DocumentScopeRetrievalValidationError:
        raise
    except (
        DocumentEmbeddingNotFoundError,
        DocumentEmbeddingNotReadyError,
        DocumentEmbeddingError,
    ) as error:
        semantic_chunks = []
        semantic_error = str(error)

    fused_chunks = fuse_retrieval_results(
        keyword_chunks=keyword_chunks,
        semantic_chunks=semantic_chunks,
        limit=cleaned_limit,
    )

    wrapped = [
        ScopeRetrievedChunk(
            document=documents_by_id[item.chunk.document_id],
            retrieved=item,
            visibility=visibility,
        )
        for item in fused_chunks
        if item.chunk.document_id in documents_by_id
    ]

    return DocumentScopeRetrievalResult(
        query=cleaned_query,
        chunks=wrapped,
        document_count=len(unique_documents),
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


def select_scope_sources(
    *, retrieval_result: DocumentScopeRetrievalResult, source_ids
) -> DocumentScopeRetrievalResult:
    selected = []
    seen: set[int] = set()
    for raw_source_id in source_ids:
        try:
            source_id = int(raw_source_id)
        except (TypeError, ValueError):
            continue
        if source_id in seen or source_id < 1 or source_id > len(retrieval_result.chunks):
            continue
        seen.add(source_id)
        selected.append(retrieval_result.chunks[source_id - 1])

    if not selected:
        raise DocumentScopeRetrievalValidationError(
            "The verifier did not select a valid workspace source."
        )
    return replace(retrieval_result, chunks=selected)


def build_scope_context(
    result: DocumentScopeRetrievalResult,
    *,
    max_characters: int = RETRIEVAL_CONTEXT_CHARACTERS,
) -> str:
    if max_characters < 500:
        raise ValueError("Workspace retrieval context must allow at least 500 characters.")
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

        clean_text = PAGE_MARKER_PATTERN.sub("", str(retrieved.text or "")).strip()
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


def _clean_query(query: str) -> str:
    cleaned = " ".join(str(query or "").split()).strip()
    if not cleaned:
        raise DocumentScopeRetrievalValidationError("Enter a question to search the workspace.")
    if len(cleaned) > MAX_QUERY_CHARACTERS:
        raise DocumentScopeRetrievalValidationError(
            f"The question is too long. Use at most {MAX_QUERY_CHARACTERS:,} characters."
        )
    return cleaned


def _validate_limit(limit: int) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError) as error:
        raise DocumentScopeRetrievalValidationError("The result limit is invalid.") from error
    max_allowed = min(MAX_RESULT_LIMIT, get_resource_limits().max_retrieval_results)
    if value < 1 or value > max_allowed:
        raise DocumentScopeRetrievalValidationError(
            f"The result limit must be between 1 and {max_allowed}."
        )
    return value


def _page_label(retrieved: ScopeRetrievedChunk) -> str:
    if retrieved.page_start and retrieved.page_end and retrieved.page_start != retrieved.page_end:
        return f"{retrieved.page_start}-{retrieved.page_end}"
    page = retrieved.page_start or retrieved.page_end
    return str(page) if page else ""


def _clean_label(value: Any, max_length: int) -> str:
    return " ".join(str(value or "").split()).strip()[:max_length]


def _mode(*, keyword_count: int, semantic_count: int, semantic_error: str | None) -> str:
    if semantic_error:
        return "keyword_fallback"
    if keyword_count and semantic_count:
        return "hybrid"
    if semantic_count:
        return "semantic"
    return "keyword"

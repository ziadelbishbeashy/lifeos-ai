"""Project-wide multi-document hybrid retrieval for LifeOS Document Brain.

Step 12 reuses the existing document chunking, BM25, embedding and hybrid-fusion
primitives. The only new layer is project scoping: every candidate chunk must
belong to a document linked to the owned project before it can enter retrieval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from models import Document, DocumentChunk, Project
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
    rank_document_chunks,
)
from services.document_semantic_retrieval_service import (
    rank_semantic_document_chunks,
)
from services.document_version_service import (
    current_document_filter,
)


DEFAULT_RESULT_LIMIT = 8
MAX_RESULT_LIMIT = 12
GLOBAL_CANDIDATE_LIMIT = 12
MAX_QUERY_CHARACTERS = 2_000
RETRIEVAL_CONTEXT_CHARACTERS = 16_000

PAGE_MARKER_PATTERN = re.compile(
    r"^--- Page\s+\d+\s+---\s*",
    flags=re.MULTILINE,
)


class ProjectDocumentRetrievalError(RuntimeError):
    """Base error for project-wide document retrieval."""


class ProjectDocumentRetrievalNotFoundError(
    ProjectDocumentRetrievalError
):
    """Raised when a project is missing or not owned."""


class ProjectDocumentRetrievalNotReadyError(
    ProjectDocumentRetrievalError
):
    """Raised when a project has no searchable linked document."""


class ProjectDocumentRetrievalValidationError(
    ProjectDocumentRetrievalError
):
    """Raised when project retrieval input is invalid."""


@dataclass(frozen=True)
class ProjectRetrievedDocumentChunk:
    """One globally ranked passage with project/document provenance."""

    document: Document
    retrieved: HybridRetrievedDocumentChunk

    @property
    def chunk(self) -> DocumentChunk:
        return self.retrieved.chunk

    @property
    def score(self) -> float:
        return self.retrieved.score

    @property
    def keyword_score(self) -> float | None:
        return self.retrieved.keyword_score

    @property
    def semantic_score(self) -> float | None:
        return self.retrieved.semantic_score

    @property
    def keyword_rank(self) -> int | None:
        return self.retrieved.keyword_rank

    @property
    def semantic_rank(self) -> int | None:
        return self.retrieved.semantic_rank

    @property
    def matched_terms(self) -> tuple[str, ...]:
        return self.retrieved.matched_terms

    @property
    def page_start(self) -> int | None:
        return self.retrieved.page_start

    @property
    def page_end(self) -> int | None:
        return self.retrieved.page_end

    @property
    def section_title(self) -> str | None:
        return self.retrieved.section_title

    @property
    def text(self) -> str:
        return self.retrieved.text

    def source(self) -> dict[str, Any]:
        """Return trusted source metadata for storage and UI."""

        base_source = self.retrieved.source()

        return {
            "project_id": self.document.project_id,
            "document_id": self.document.id,
            "filename": self.document.filename,
            "page": base_source.get("page"),
            "section": base_source.get("section"),
            "evidence": base_source.get("evidence"),
            "chunk_id": self.chunk.id,
            "chunk_index": self.chunk.chunk_index,
            "content_type": base_source.get("content_type", "text"),
            "table_id": base_source.get("table_id"),
            "visibility": "project_owner",
        }


@dataclass(frozen=True)
class ProjectDocumentRetrievalResult:
    """Globally ranked evidence from every searchable PDF in one project."""

    project: Project
    query: str
    chunks: list[ProjectRetrievedDocumentChunk]
    project_document_count: int
    searchable_document_count: int
    skipped_document_count: int
    mode: str
    semantic_error: str | None
    index_rebuilt_count: int
    chunks_rebuilt_count: int
    embedded_count: int
    reused_count: int


def retrieve_owned_project_document_chunks(
    *,
    project_id: int,
    user_id: int,
    query: str,
    limit: int = DEFAULT_RESULT_LIMIT,
    force_embeddings: bool = False,
) -> ProjectDocumentRetrievalResult:
    """Search all readable documents linked to one owned project."""

    cleaned_query = _clean_query(query)
    cleaned_limit = _validate_limit(limit)

    project = (
        Project.query
        .filter_by(
            id=project_id,
            user_id=user_id,
        )
        .first()
    )

    if project is None:
        raise ProjectDocumentRetrievalNotFoundError(
            "The project could not be found."
        )

    documents = (
        Document.query
        .filter(
            Document.project_id == project.id,
            current_document_filter(),
        )
        .order_by(
            Document.uploaded_at.desc(),
            Document.id.desc(),
        )
        .all()
    )

    if not documents:
        raise ProjectDocumentRetrievalNotReadyError(
            "This project does not have any linked documents yet."
        )

    searchable_documents: list[Document] = []
    all_chunks: list[DocumentChunk] = []
    document_by_id: dict[int, Document] = {}
    skipped_document_count = 0
    index_rebuilt_count = 0

    # First build one globally comparable keyword corpus across the project.
    for document in documents:
        try:
            indexed = ensure_owned_document_chunks(
                document_id=document.id,
                user_id=user_id,
            )
        except (
            DocumentChunkNotReadyError,
            DocumentChunkNotFoundError,
        ):
            skipped_document_count += 1
            continue
        except DocumentChunkError as error:
            raise ProjectDocumentRetrievalError(
                "LifeOS could not prepare the linked project documents for search."
            ) from error

        if not indexed.chunks:
            skipped_document_count += 1
            continue

        # Defensive project boundary check even though the chunk service already
        # verifies ownership through the document's project.
        if indexed.document.project_id != project.id:
            raise ProjectDocumentRetrievalNotFoundError(
                "The project document could not be accessed."
            )

        searchable_documents.append(indexed.document)
        document_by_id[indexed.document.id] = indexed.document
        all_chunks.extend(indexed.chunks)
        index_rebuilt_count += int(bool(indexed.rebuilt))

    if not searchable_documents or not all_chunks:
        raise ProjectDocumentRetrievalNotReadyError(
            "None of the linked project documents contains searchable text yet."
        )

    keyword_chunks = rank_document_chunks(
        query=cleaned_query,
        chunks=all_chunks,
        limit=GLOBAL_CANDIDATE_LIMIT,
    )

    semantic_chunks = []
    semantic_error: str | None = None
    chunks_rebuilt_count = 0
    embedded_count = 0
    reused_count = 0

    try:
        embedded_chunks: list[DocumentChunk] = []
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
                    "Project document embeddings use inconsistent configurations."
                )

            embedded_chunks.extend(embedded.chunks)
            embedded_count += embedded.embedded_count
            reused_count += embedded.reused_count
            chunks_rebuilt_count += int(bool(embedded.chunks_rebuilt))

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
                "The question and project document embeddings use different configurations."
            )

        semantic_chunks = rank_semantic_document_chunks(
            question_embedding=question_embedding,
            chunks=embedded_chunks,
            limit=GLOBAL_CANDIDATE_LIMIT,
        )

    except (
        DocumentEmbeddingNotFoundError,
        DocumentEmbeddingNotReadyError,
        DocumentEmbeddingError,
    ) as error:
        # Preserve availability. Keyword retrieval already uses the complete
        # searchable project corpus, so a semantic outage must not block Q&A.
        semantic_chunks = []
        semantic_error = str(error)

    fused = fuse_retrieval_results(
        keyword_chunks=keyword_chunks,
        semantic_chunks=semantic_chunks,
        limit=cleaned_limit,
    )

    wrapped: list[ProjectRetrievedDocumentChunk] = []

    for retrieved in fused:
        document = document_by_id.get(retrieved.chunk.document_id)

        if document is None:
            # Fail closed: a source without owned project provenance is never
            # allowed to enter the answer context.
            continue

        wrapped.append(
            ProjectRetrievedDocumentChunk(
                document=document,
                retrieved=retrieved,
            )
        )

    return ProjectDocumentRetrievalResult(
        project=project,
        query=cleaned_query,
        chunks=wrapped,
        project_document_count=len(documents),
        searchable_document_count=len(searchable_documents),
        skipped_document_count=skipped_document_count,
        mode=_retrieval_mode(
            keyword_count=len(keyword_chunks),
            semantic_count=len(semantic_chunks),
            semantic_error=semantic_error,
        ),
        semantic_error=semantic_error,
        index_rebuilt_count=index_rebuilt_count,
        chunks_rebuilt_count=chunks_rebuilt_count,
        embedded_count=embedded_count,
        reused_count=reused_count,
    )


def select_project_retrieval_sources(
    *,
    retrieval_result: ProjectDocumentRetrievalResult,
    source_ids: tuple[int, ...] | list[int],
) -> ProjectDocumentRetrievalResult:
    """Return only verifier-approved numbered sources in stable order."""

    selected: list[ProjectRetrievedDocumentChunk] = []
    seen: set[int] = set()

    for raw_source_id in source_ids:
        try:
            source_id = int(raw_source_id)
        except (TypeError, ValueError):
            continue

        if source_id in seen:
            continue

        if source_id < 1 or source_id > len(retrieval_result.chunks):
            continue

        seen.add(source_id)
        selected.append(retrieval_result.chunks[source_id - 1])

    if not selected:
        raise ProjectDocumentRetrievalValidationError(
            "The verifier did not select a valid project document source."
        )

    return replace(
        retrieval_result,
        chunks=selected,
    )


def build_project_retrieval_context(
    result: ProjectDocumentRetrievalResult,
    *,
    max_characters: int = RETRIEVAL_CONTEXT_CHARACTERS,
) -> str:
    """Build numbered, document-aware source blocks for verifier/answer models."""

    if max_characters < 500:
        raise ValueError(
            "Project retrieval context must allow at least 500 characters."
        )

    blocks: list[str] = []
    used_characters = 0

    for source_id, retrieved in enumerate(result.chunks, start=1):
        location_parts = [
            f'Document "{_clean_label(retrieved.document.filename, 220)}"'
        ]

        page = _page_label(retrieved)
        if page:
            location_parts.append(f"Page {page}")

        section = _clean_label(retrieved.section_title, 220)
        if section:
            location_parts.append(section)

        clean_text = PAGE_MARKER_PATTERN.sub(
            "",
            str(retrieved.text or ""),
        ).strip()

        block = (
            f"[Source {source_id} | {' | '.join(location_parts)}]\n"
            f"{clean_text}"
        )

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


def _page_label(retrieved: ProjectRetrievedDocumentChunk) -> str:
    if (
        retrieved.page_start
        and retrieved.page_end
        and retrieved.page_start != retrieved.page_end
    ):
        return f"{retrieved.page_start}-{retrieved.page_end}"

    page = retrieved.page_start or retrieved.page_end
    return str(page) if page else ""


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


def _clean_query(query: str) -> str:
    cleaned = " ".join(str(query or "").split()).strip()

    if not cleaned:
        raise ProjectDocumentRetrievalValidationError(
            "Please enter a project document question."
        )

    if len(cleaned) > MAX_QUERY_CHARACTERS:
        raise ProjectDocumentRetrievalValidationError(
            "The project document question cannot exceed "
            f"{MAX_QUERY_CHARACTERS:,} characters."
        )

    return cleaned


def _validate_limit(limit: int) -> int:
    try:
        cleaned = int(limit)
    except (TypeError, ValueError) as error:
        raise ProjectDocumentRetrievalValidationError(
            "The result limit must be a number."
        ) from error

    if cleaned < 1:
        raise ProjectDocumentRetrievalValidationError(
            "The result limit must be at least 1."
        )

    if cleaned > MAX_RESULT_LIMIT:
        raise ProjectDocumentRetrievalValidationError(
            f"The result limit cannot exceed {MAX_RESULT_LIMIT}."
        )

    return cleaned


def _clean_label(value: Any, max_characters: int) -> str:
    return " ".join(str(value or "").split()).strip()[:max_characters]

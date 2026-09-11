"""Grounded document evidence adapter for general Ask LifeOS reasoning.

This wrapper reuses the authoritative project Document Brain retrieval pipeline.
It never exposes embeddings/chunk IDs to the model-facing public payload and
fails soft when a project has no searchable documents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.project_document_retrieval_service import (
    ProjectDocumentRetrievalError,
    build_project_retrieval_context,
    retrieve_owned_project_document_chunks,
)
from services.document_hybrid_retrieval_service import (
    DocumentHybridRetrievalError,
    build_hybrid_retrieval_context,
    retrieve_owned_document_chunks_hybrid,
)
from services.document_collection_retrieval_service import (
    CollectionRetrievalError,
    build_collection_context,
    retrieve_owned_collection_chunks,
)
from services.document_scope_retrieval_service import (
    DocumentScopeRetrievalError,
    build_scope_context,
    retrieve_owned_document_set,
)
from services.module_question_workflow_service import (
    ModuleQuestionWorkflowError,
    list_owned_module_scope_documents,
)


DEFAULT_GENERAL_RAG_RESULTS = 6
MAX_GENERAL_RAG_CONTEXT = 12_000


@dataclass(frozen=True)
class IntelligenceDocumentSource:
    source_id: str
    document_id: int
    filename: str
    page: Any = None
    section: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.source_id,
            "document_id": self.document_id,
            "filename": self.filename,
            "page": self.page,
            "section": self.section,
        }


@dataclass(frozen=True)
class IntelligenceRAGEvidence:
    context: str
    sources: tuple[IntelligenceDocumentSource, ...]
    retrieval_mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources": [item.to_dict() for item in self.sources],
            "source_count": len(self.sources),
            "retrieval_mode": self.retrieval_mode,
            "verified_grounding": True,
        }

    @property
    def source_ids(self) -> frozenset[str]:
        return frozenset(item.source_id for item in self.sources)


def retrieve_project_reasoning_evidence(
    *,
    owner_id: int,
    project_id: int,
    query: str,
) -> IntelligenceRAGEvidence | None:
    """Return bounded project-document evidence or ``None`` when unavailable."""

    try:
        result = retrieve_owned_project_document_chunks(
            project_id=int(project_id),
            user_id=int(owner_id),
            query=str(query or "").strip(),
            limit=DEFAULT_GENERAL_RAG_RESULTS,
        )
    except ProjectDocumentRetrievalError:
        return None

    if not result.chunks:
        return None

    raw_context = build_project_retrieval_context(
        result,
        max_characters=MAX_GENERAL_RAG_CONTEXT,
    )
    # The authoritative retriever numbers sources as [Source 1]. General
    # reasoning uses D1/D2 so document and web citations can coexist clearly.
    context = raw_context
    sources: list[IntelligenceDocumentSource] = []
    for index, chunk in enumerate(result.chunks, start=1):
        context = context.replace(f"[Source {index} |", f"[D{index} |")
        source = chunk.source()
        sources.append(
            IntelligenceDocumentSource(
                source_id=f"D{index}",
                document_id=int(chunk.document.id),
                filename=str(chunk.document.filename or f"Document {chunk.document.id}"),
                page=source.get("page"),
                section=(str(source.get("section") or "").strip() or None),
            )
        )

    return IntelligenceRAGEvidence(
        context=context,
        sources=tuple(sources),
        retrieval_mode=str(result.mode or "hybrid"),
    )


def _renumber_context(raw_context: str, count: int) -> str:
    context = str(raw_context or "")
    for index in range(1, count + 1):
        context = context.replace(f"[Source {index} |", f"[D{index} |")
    return context


def _sources_from_scoped_chunks(chunks: list[Any]) -> tuple[IntelligenceDocumentSource, ...]:
    sources: list[IntelligenceDocumentSource] = []
    for index, retrieved in enumerate(chunks, start=1):
        source = retrieved.source() if hasattr(retrieved, "source") else {}
        document = getattr(retrieved, "document", None)
        document_id = source.get("document_id") or getattr(document, "id", None)
        filename = source.get("filename") or getattr(document, "filename", None)
        if document_id is None:
            continue
        sources.append(
            IntelligenceDocumentSource(
                source_id=f"D{index}",
                document_id=int(document_id),
                filename=str(filename or f"Document {document_id}"),
                page=source.get("page"),
                section=(str(source.get("section") or "").strip() or None),
            )
        )
    return tuple(sources)


def retrieve_context_reasoning_evidence(
    *,
    owner_id: int,
    context_type: str,
    context_id: int,
    query: str,
    parent_id: int | None = None,
) -> IntelligenceRAGEvidence | None:
    """Reuse the authoritative RAG stack for any explicit Ask LifeOS scope.

    The selected context narrows trusted document evidence; it never grants new
    ownership. Each underlying retriever independently revalidates ownership.
    """

    kind = str(context_type or "").strip().lower()
    cleaned_query = str(query or "").strip()
    if kind == "project":
        return retrieve_project_reasoning_evidence(
            owner_id=int(owner_id), project_id=int(context_id), query=cleaned_query
        )

    if kind == "document":
        try:
            result = retrieve_owned_document_chunks_hybrid(
                document_id=int(context_id),
                user_id=int(owner_id),
                query=cleaned_query,
                limit=DEFAULT_GENERAL_RAG_RESULTS,
            )
        except DocumentHybridRetrievalError:
            return None
        if not result.chunks:
            return None
        raw_context = build_hybrid_retrieval_context(
            result, max_characters=MAX_GENERAL_RAG_CONTEXT
        )
        sources: list[IntelligenceDocumentSource] = []
        for index, chunk in enumerate(result.chunks, start=1):
            source = chunk.source()
            sources.append(
                IntelligenceDocumentSource(
                    source_id=f"D{index}",
                    document_id=int(result.document.id),
                    filename=str(result.document.filename or f"Document {result.document.id}"),
                    page=source.get("page"),
                    section=(str(source.get("section") or "").strip() or None),
                )
            )
        return IntelligenceRAGEvidence(
            context=_renumber_context(raw_context, len(result.chunks)),
            sources=tuple(sources),
            retrieval_mode=str(result.mode or "hybrid"),
        )

    if kind == "collection":
        try:
            result = retrieve_owned_collection_chunks(
                collection_id=int(context_id),
                user_id=int(owner_id),
                query=cleaned_query,
                limit=DEFAULT_GENERAL_RAG_RESULTS,
            )
        except CollectionRetrievalError:
            return None
        if not result.chunks:
            return None
        raw_context = build_collection_context(
            result, max_characters=MAX_GENERAL_RAG_CONTEXT
        )
        return IntelligenceRAGEvidence(
            context=_renumber_context(raw_context, len(result.chunks)),
            sources=_sources_from_scoped_chunks(list(result.chunks)),
            retrieval_mode=str(result.mode or "hybrid"),
        )

    if kind in {"module", "lecture"}:
        module_id = int(context_id) if kind == "module" else int(parent_id or 0)
        lecture_id = int(context_id) if kind == "lecture" else None
        if module_id <= 0:
            return None
        try:
            documents = list_owned_module_scope_documents(
                module_id=module_id,
                user_id=int(owner_id),
                lecture_id=lecture_id,
            )
            result = retrieve_owned_document_set(
                documents=documents,
                user_id=int(owner_id),
                query=cleaned_query,
                limit=DEFAULT_GENERAL_RAG_RESULTS,
                visibility="module_owner" if kind == "module" else "lecture_owner",
            )
        except (ModuleQuestionWorkflowError, DocumentScopeRetrievalError):
            return None
        if not result.chunks:
            return None
        raw_context = build_scope_context(
            result, max_characters=MAX_GENERAL_RAG_CONTEXT
        )
        return IntelligenceRAGEvidence(
            context=_renumber_context(raw_context, len(result.chunks)),
            sources=_sources_from_scoped_chunks(list(result.chunks)),
            retrieval_mode=str(result.mode or "hybrid"),
        )

    return None

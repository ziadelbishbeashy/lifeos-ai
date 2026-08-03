"""Tests for hybrid keyword and semantic document retrieval."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from models import Document, DocumentChunk

import services.document_hybrid_retrieval_service as hybrid_service

from services.document_hybrid_retrieval_service import (
    DocumentHybridRetrievalError,
    DocumentHybridRetrievalValidationError,
    build_hybrid_retrieval_context,
    fuse_retrieval_results,
    retrieve_owned_document_chunks_hybrid,
)
from services.document_retrieval_service import (
    DocumentRetrievalResult,
    RetrievedDocumentChunk,
)
from services.document_semantic_retrieval_service import (
    DocumentSemanticRetrievalError,
    DocumentSemanticRetrievalResult,
    SemanticRetrievedDocumentChunk,
)


def create_document() -> Document:
    """Create an in-memory document for retrieval tests."""

    return Document(
        id=1,
        project_id=1,
        filename="requirements.pdf",
        file_path="stored/requirements.pdf",
        extracted_text="Readable document text.",
    )


def create_chunk(
    *,
    chunk_index: int,
    page: int,
    text: str,
    section_title: str | None = None,
) -> DocumentChunk:
    """Create an in-memory document chunk."""

    return DocumentChunk(
        id=chunk_index + 1,
        document_id=1,
        user_id=1,
        chunk_index=chunk_index,
        page_start=page,
        page_end=page,
        section_title=section_title,
        text=(
            f"--- Page {page} ---\n"
            f"{text}"
        ),
        character_count=len(text),
        source_fingerprint="a" * 64,
        embedding_json=json.dumps(
            [
                1.0,
                0.0,
                0.0,
                0.0,
            ]
        ),
        embedding_provider="gemini",
        embedding_model="test-embedding-model",
        embedding_dimensions=4,
        embedding_fingerprint="b" * 64,
        embedded_at=datetime.utcnow(),
    )


def keyword_result(
    *,
    chunk: DocumentChunk,
    score: float,
    matched_terms: tuple[str, ...] = (),
) -> RetrievedDocumentChunk:
    """Create one fake BM25 result."""

    return RetrievedDocumentChunk(
        chunk=chunk,
        score=score,
        matched_terms=matched_terms,
    )


def semantic_result(
    *,
    chunk: DocumentChunk,
    score: float,
) -> SemanticRetrievedDocumentChunk:
    """Create one fake semantic result."""

    return SemanticRetrievedDocumentChunk(
        chunk=chunk,
        score=score,
    )


def test_shared_chunk_receives_strongest_hybrid_rank():
    shared_chunk = create_chunk(
        chunk_index=0,
        page=2,
        section_title="Account Recovery",
        text=(
            "Users can reset forgotten passwords "
            "using a secure email link."
        ),
    )

    keyword_only_chunk = create_chunk(
        chunk_index=1,
        page=3,
        text="Password security rules are documented.",
    )

    semantic_only_chunk = create_chunk(
        chunk_index=2,
        page=4,
        text="Account access can be restored.",
    )

    ranked = fuse_retrieval_results(
        keyword_chunks=[
            keyword_result(
                chunk=shared_chunk,
                score=8.5,
                matched_terms=(
                    "password",
                ),
            ),
            keyword_result(
                chunk=keyword_only_chunk,
                score=5.0,
                matched_terms=(
                    "password",
                ),
            ),
        ],
        semantic_chunks=[
            semantic_result(
                chunk=shared_chunk,
                score=0.96,
            ),
            semantic_result(
                chunk=semantic_only_chunk,
                score=0.91,
            ),
        ],
    )

    assert ranked[0].chunk.chunk_index == 0

    assert ranked[0].retrieval_methods == (
        "keyword",
        "semantic",
    )

    assert ranked[0].keyword_rank == 1
    assert ranked[0].semantic_rank == 1

    assert (
        ranked[0].matched_terms
        == ("password",)
    )


def test_keyword_only_and_semantic_only_chunks_are_retained():
    keyword_chunk = create_chunk(
        chunk_index=0,
        page=1,
        text="Exact authentication requirement.",
    )

    semantic_chunk = create_chunk(
        chunk_index=1,
        page=2,
        text="Users confirm their identity.",
    )

    ranked = fuse_retrieval_results(
        keyword_chunks=[
            keyword_result(
                chunk=keyword_chunk,
                score=4.2,
            ),
        ],
        semantic_chunks=[
            semantic_result(
                chunk=semantic_chunk,
                score=0.88,
            ),
        ],
    )

    indexes = {
        result.chunk.chunk_index
        for result in ranked
    }

    assert indexes == {
        0,
        1,
    }

    keyword_item = next(
        result
        for result in ranked
        if result.chunk.chunk_index == 0
    )

    semantic_item = next(
        result
        for result in ranked
        if result.chunk.chunk_index == 1
    )

    assert keyword_item.retrieval_methods == (
        "keyword",
    )

    assert semantic_item.retrieval_methods == (
        "semantic",
    )


def test_hybrid_fusion_respects_result_limit():
    chunks = [
        create_chunk(
            chunk_index=index,
            page=index + 1,
            text=f"Document information {index}.",
        )
        for index in range(5)
    ]

    ranked = fuse_retrieval_results(
        keyword_chunks=[
            keyword_result(
                chunk=chunk,
                score=float(
                    10 - chunk.chunk_index
                ),
            )
            for chunk in chunks
        ],
        semantic_chunks=[
            semantic_result(
                chunk=chunk,
                score=(
                    1.0
                    - chunk.chunk_index * 0.1
                ),
            )
            for chunk in chunks
        ],
        limit=2,
    )

    assert len(ranked) == 2


def test_weights_are_normalized_before_fusion():
    chunk = create_chunk(
        chunk_index=0,
        page=1,
        text="Authentication information.",
    )

    decimal_weights = fuse_retrieval_results(
        keyword_chunks=[
            keyword_result(
                chunk=chunk,
                score=5.0,
            ),
        ],
        semantic_chunks=[],
        keyword_weight=0.7,
        semantic_weight=0.3,
    )

    percentage_weights = fuse_retrieval_results(
        keyword_chunks=[
            keyword_result(
                chunk=chunk,
                score=5.0,
            ),
        ],
        semantic_chunks=[],
        keyword_weight=70,
        semantic_weight=30,
    )

    assert (
        decimal_weights[0].score
        == percentage_weights[0].score
    )


def test_invalid_zero_weights_are_rejected():
    with pytest.raises(
        DocumentHybridRetrievalValidationError,
        match="At least one retrieval weight",
    ):
        fuse_retrieval_results(
            keyword_chunks=[],
            semantic_chunks=[],
            keyword_weight=0,
            semantic_weight=0,
        )


def test_hybrid_context_contains_sources_and_pages():
    chunk = create_chunk(
        chunk_index=0,
        page=6,
        section_title="Deployment",
        text=(
            "The deployment must be completed "
            "before 10 September."
        ),
    )

    document = create_document()

    fused_chunks = fuse_retrieval_results(
        keyword_chunks=[
            keyword_result(
                chunk=chunk,
                score=6.0,
                matched_terms=(
                    "deployment",
                ),
            ),
        ],
        semantic_chunks=[
            semantic_result(
                chunk=chunk,
                score=0.92,
            ),
        ],
    )

    result = (
        hybrid_service.DocumentHybridRetrievalResult(
            document=document,
            query="When is deployment due?",
            chunks=fused_chunks,
            mode="hybrid",
            keyword_result_count=1,
            semantic_result_count=1,
            index_rebuilt=False,
            chunks_rebuilt=False,
            embedded_count=0,
            reused_count=1,
            embedding_provider="gemini",
            embedding_model="test-embedding-model",
            embedding_dimensions=4,
            semantic_error=None,
        )
    )

    context = build_hybrid_retrieval_context(
        result
    )

    assert "[Source 1" in context
    assert "Page 6" in context
    assert "Deployment" in context
    assert "10 September" in context


def test_full_hybrid_retrieval_combines_both_services(
    monkeypatch,
):
    document = create_document()

    account_chunk = create_chunk(
        chunk_index=0,
        page=2,
        section_title="Account Recovery",
        text=(
            "Users reset forgotten passwords through "
            "a secure email recovery link."
        ),
    )

    dashboard_chunk = create_chunk(
        chunk_index=1,
        page=3,
        section_title="Dashboard",
        text="The dashboard displays project progress.",
    )

    fake_keyword_result = DocumentRetrievalResult(
        document=document,
        query="How can users recover account access?",
        chunks=[
            keyword_result(
                chunk=account_chunk,
                score=7.0,
                matched_terms=(
                    "account",
                ),
            ),
        ],
        index_rebuilt=False,
    )

    fake_semantic_result = (
        DocumentSemanticRetrievalResult(
            document=document,
            query=(
                "How can users recover account access?"
            ),
            chunks=[
                semantic_result(
                    chunk=account_chunk,
                    score=0.97,
                ),
                semantic_result(
                    chunk=dashboard_chunk,
                    score=0.35,
                ),
            ],
            embedded_count=0,
            reused_count=2,
            chunks_rebuilt=False,
            provider="gemini",
            model="test-embedding-model",
            dimensions=4,
        )
    )

    monkeypatch.setattr(
        hybrid_service,
        "retrieve_owned_document_chunks",
        lambda **kwargs: fake_keyword_result,
    )

    monkeypatch.setattr(
        hybrid_service,
        "retrieve_owned_document_chunks_semantically",
        lambda **kwargs: fake_semantic_result,
    )

    result = retrieve_owned_document_chunks_hybrid(
        document_id=1,
        user_id=1,
        query=(
            "How can users recover account access?"
        ),
    )

    assert result.mode == "hybrid"

    assert result.keyword_result_count == 1
    assert result.semantic_result_count == 2

    assert result.chunks[0].chunk.chunk_index == 0

    assert result.chunks[0].retrieval_methods == (
        "keyword",
        "semantic",
    )

    assert result.embedding_provider == "gemini"

    assert (
        result.embedding_model
        == "test-embedding-model"
    )


def test_semantic_failure_falls_back_to_keyword_results(
    monkeypatch,
):
    document = create_document()

    keyword_chunk = create_chunk(
        chunk_index=0,
        page=1,
        text="The report deadline is 20 August.",
    )

    fake_keyword_result = DocumentRetrievalResult(
        document=document,
        query="What is the report deadline?",
        chunks=[
            keyword_result(
                chunk=keyword_chunk,
                score=8.0,
                matched_terms=(
                    "report",
                    "deadline",
                ),
            ),
        ],
        index_rebuilt=False,
    )

    monkeypatch.setattr(
        hybrid_service,
        "retrieve_owned_document_chunks",
        lambda **kwargs: fake_keyword_result,
    )

    def fail_semantic_retrieval(**kwargs):
        raise DocumentSemanticRetrievalError(
            "Embedding provider unavailable."
        )

    monkeypatch.setattr(
        hybrid_service,
        "retrieve_owned_document_chunks_semantically",
        fail_semantic_retrieval,
    )

    result = retrieve_owned_document_chunks_hybrid(
        document_id=1,
        user_id=1,
        query="What is the report deadline?",
    )

    assert result.mode == "keyword_fallback"
    assert result.semantic_result_count == 0
    assert result.keyword_result_count == 1

    assert len(result.chunks) == 1

    assert result.chunks[0].retrieval_methods == (
        "keyword",
    )

    assert (
        "Embedding provider unavailable"
        in result.semantic_error
    )


def test_semantic_failure_without_keyword_evidence_raises(
    monkeypatch,
):
    document = create_document()

    empty_keyword_result = DocumentRetrievalResult(
        document=document,
        query="Unmatched semantic question",
        chunks=[],
        index_rebuilt=False,
    )

    monkeypatch.setattr(
        hybrid_service,
        "retrieve_owned_document_chunks",
        lambda **kwargs: empty_keyword_result,
    )

    def fail_semantic_retrieval(**kwargs):
        raise DocumentSemanticRetrievalError(
            "Embedding provider unavailable."
        )

    monkeypatch.setattr(
        hybrid_service,
        "retrieve_owned_document_chunks_semantically",
        fail_semantic_retrieval,
    )

    with pytest.raises(
        DocumentHybridRetrievalError,
        match="Embedding provider unavailable",
    ):
        retrieve_owned_document_chunks_hybrid(
            document_id=1,
            user_id=1,
            query="Unmatched semantic question",
        )
"""Tests for direct search inside a Document Brain PDF."""

from types import SimpleNamespace

import pytest

from services import document_search_service as service
from services.document_chunk_service import (
    DocumentChunkNotFoundError,
)
from services.document_hybrid_retrieval_service import (
    DocumentHybridRetrievalError,
)
from services.document_search_service import (
    DocumentSearchError,
    DocumentSearchNotFoundError,
    DocumentSearchValidationError,
    search_owned_document,
)


def make_chunk(
    *,
    chunk_id: int,
    chunk_index: int,
    text: str,
    page: int,
    section: str,
):
    return SimpleNamespace(
        id=chunk_id,
        chunk_index=chunk_index,
        text=text,
        page_start=page,
        page_end=page,
        section_title=section,
    )


def make_hybrid_chunk(
    chunk,
    *,
    keyword_rank=None,
    semantic_rank=None,
    keyword_score=None,
    semantic_score=None,
    matched_terms=(),
):
    methods = []

    if keyword_rank is not None:
        methods.append("keyword")

    if semantic_rank is not None:
        methods.append("semantic")

    return SimpleNamespace(
        chunk=chunk,
        keyword_rank=keyword_rank,
        semantic_rank=semantic_rank,
        keyword_score=keyword_score,
        semantic_score=semantic_score,
        matched_terms=matched_terms,
        retrieval_methods=tuple(methods),
    )


def configure_index(monkeypatch, chunks):
    document = SimpleNamespace(
        id=2,
        filename="architecture.pdf",
    )

    monkeypatch.setattr(
        service,
        "ensure_owned_document_chunks",
        lambda **kwargs: SimpleNamespace(
            document=document,
            chunks=chunks,
            rebuilt=False,
        ),
    )

    return document


def test_exact_phrase_is_ranked_before_broader_hybrid_match(
    monkeypatch,
):
    broad = make_chunk(
        chunk_id=10,
        chunk_index=0,
        text=(
            "--- Page 2 ---\n"
            "Account ownership is checked before project records are returned."
        ),
        page=2,
        section="Ownership",
    )

    exact = make_chunk(
        chunk_id=11,
        chunk_index=1,
        text=(
            "--- Page 8 ---\n"
            "LifeOS follows a private by default collaboration model."
        ),
        page=8,
        section="Privacy",
    )

    document = configure_index(
        monkeypatch,
        [broad, exact],
    )

    monkeypatch.setattr(
        service,
        "retrieve_owned_document_chunks_hybrid",
        lambda **kwargs: SimpleNamespace(
            document=document,
            query=kwargs["query"],
            chunks=[
                make_hybrid_chunk(
                    broad,
                    keyword_rank=1,
                    semantic_rank=1,
                    keyword_score=2.5,
                    semantic_score=0.73,
                    matched_terms=("private",),
                ),
                make_hybrid_chunk(
                    exact,
                    keyword_rank=2,
                    semantic_rank=2,
                    keyword_score=1.8,
                    semantic_score=0.66,
                    matched_terms=("private", "default"),
                ),
            ],
            mode="hybrid",
            keyword_result_count=2,
            semantic_result_count=2,
            semantic_error=None,
            chunks_rebuilt=False,
            embedded_count=0,
            reused_count=2,
        ),
    )

    result = search_owned_document(
        document_id=2,
        user_id=1,
        query="private by default",
    )

    assert result.result_count == 2
    assert result.hits[0].chunk_id == 11
    assert result.hits[0].exact_phrase is True
    assert result.hits[0].match_strength == "Exact"
    assert "private by default" in result.hits[0].preview.casefold()
    assert result.hits[1].chunk_id == 10


def test_semantic_result_can_be_returned_without_exact_phrase(
    monkeypatch,
):
    chunk = make_chunk(
        chunk_id=21,
        chunk_index=3,
        text=(
            "--- Page 5 ---\n"
            "Every project query verifies the authenticated owner before data is returned."
        ),
        page=5,
        section="Access control",
    )

    document = configure_index(
        monkeypatch,
        [chunk],
    )

    monkeypatch.setattr(
        service,
        "retrieve_owned_document_chunks_hybrid",
        lambda **kwargs: SimpleNamespace(
            document=document,
            query=kwargs["query"],
            chunks=[
                make_hybrid_chunk(
                    chunk,
                    semantic_rank=1,
                    semantic_score=0.78,
                )
            ],
            mode="semantic_only",
            keyword_result_count=0,
            semantic_result_count=1,
            semantic_error=None,
            chunks_rebuilt=False,
            embedded_count=0,
            reused_count=1,
        ),
    )

    result = search_owned_document(
        document_id=2,
        user_id=1,
        query="how users are kept separate",
    )

    assert result.result_count == 1
    assert result.hits[0].method_label == "Semantic"
    assert result.hits[0].semantic_score == 0.78
    assert "authenticated owner" in result.hits[0].preview


def test_exact_search_survives_hybrid_provider_failure(
    monkeypatch,
):
    chunk = make_chunk(
        chunk_id=31,
        chunk_index=0,
        text="--- Page 1 ---\nThe release date is 2026-09-10.",
        page=1,
        section="Schedule",
    )

    configure_index(
        monkeypatch,
        [chunk],
    )

    def fail_hybrid(**kwargs):
        raise DocumentHybridRetrievalError(
            "Embedding provider temporarily unavailable."
        )

    monkeypatch.setattr(
        service,
        "retrieve_owned_document_chunks_hybrid",
        fail_hybrid,
    )

    result = search_owned_document(
        document_id=2,
        user_id=1,
        query="release date",
    )

    assert result.result_count == 1
    assert result.mode == "exact_only"
    assert result.semantic_fallback is True
    assert result.hits[0].method_label == "Exact phrase"


def test_hybrid_failure_without_exact_match_is_reported(
    monkeypatch,
):
    chunk = make_chunk(
        chunk_id=41,
        chunk_index=0,
        text="--- Page 1 ---\nArchitecture overview.",
        page=1,
        section="Overview",
    )

    configure_index(
        monkeypatch,
        [chunk],
    )

    monkeypatch.setattr(
        service,
        "retrieve_owned_document_chunks_hybrid",
        lambda **kwargs: (_ for _ in ()).throw(
            DocumentHybridRetrievalError(
                "Search provider failed."
            )
        ),
    )

    with pytest.raises(
        DocumentSearchError,
        match="Search provider failed",
    ):
        search_owned_document(
            document_id=2,
            user_id=1,
            query="payment schedule",
        )


def test_unowned_document_is_reported_as_not_found(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "ensure_owned_document_chunks",
        lambda **kwargs: (_ for _ in ()).throw(
            DocumentChunkNotFoundError(
                "The requested document was not found."
            )
        ),
    )

    with pytest.raises(
        DocumentSearchNotFoundError,
    ):
        search_owned_document(
            document_id=999,
            user_id=1,
            query="privacy",
        )


def test_empty_search_is_rejected_before_retrieval(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "ensure_owned_document_chunks",
        lambda **kwargs: pytest.fail(
            "Chunk retrieval should not run for an empty query."
        ),
    )

    with pytest.raises(
        DocumentSearchValidationError,
        match="Enter a word",
    ):
        search_owned_document(
            document_id=2,
            user_id=1,
            query="   ",
        )


def test_search_query_length_is_bounded():
    with pytest.raises(
        DocumentSearchValidationError,
        match="500",
    ):
        search_owned_document(
            document_id=2,
            user_id=1,
            query="x" * 501,
        )

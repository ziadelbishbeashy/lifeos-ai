"""Tests for semantic document-chunk retrieval."""

import json
from datetime import datetime

import pytest

from models import (
    Document,
    DocumentChunk,
)
import services.document_semantic_retrieval_service as semantic_service
from services.document_embedding_service import (
    DocumentEmbeddingNotFoundError,
    DocumentEmbeddingNotReadyError,
    EmbeddedDocumentChunks,
    EmbeddingConfiguration,
)
from services.document_semantic_retrieval_service import (
    DocumentSemanticRetrievalError,
    DocumentSemanticRetrievalNotFoundError,
    DocumentSemanticRetrievalNotReadyError,
    DocumentSemanticRetrievalValidationError,
    rank_semantic_document_chunks,
    retrieve_owned_document_chunks_semantically,
)


TEST_PROVIDER = "gemini"
TEST_MODEL = "test-embedding-model"
TEST_DIMENSIONS = 4


def create_chunk(
    *,
    chunk_index: int,
    page: int,
    text: str,
    embedding: list[float] | None,
    section_title: str | None = None,
) -> DocumentChunk:
    """Create one in-memory document chunk."""

    chunk = DocumentChunk(
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
    )

    if embedding is not None:
        chunk.embedding_json = json.dumps(
            embedding
        )

        chunk.embedding_provider = TEST_PROVIDER
        chunk.embedding_model = TEST_MODEL

        chunk.embedding_dimensions = len(
            embedding
        )

        chunk.embedding_fingerprint = "b" * 64
        chunk.embedded_at = datetime.utcnow()

    return chunk


def create_configuration(
    *,
    model: str = TEST_MODEL,
    dimensions: int = TEST_DIMENSIONS,
) -> EmbeddingConfiguration:
    """Create a fake embedding configuration."""

    return EmbeddingConfiguration(
        provider=TEST_PROVIDER,
        api_key="test-api-key",
        model=model,
        dimensions=dimensions,
    )


def create_embedded_document(
    chunks: list[DocumentChunk],
) -> EmbeddedDocumentChunks:
    """Create a fake embedded-document result."""

    document = Document(
        id=1,
        project_id=1,
        filename="requirements.pdf",
        file_path="stored/requirements.pdf",
        extracted_text="Readable document text.",
    )

    return EmbeddedDocumentChunks(
        document=document,
        chunks=chunks,
        embedded_count=len(chunks),
        reused_count=0,
        chunks_rebuilt=False,
        provider=TEST_PROVIDER,
        model=TEST_MODEL,
        dimensions=TEST_DIMENSIONS,
    )


def test_semantic_ranking_returns_most_similar_chunk_first():
    chunks = [
        create_chunk(
            chunk_index=0,
            page=1,
            text="General project overview.",
            embedding=[
                0.0,
                1.0,
                0.0,
                0.0,
            ],
        ),
        create_chunk(
            chunk_index=1,
            page=2,
            text=(
                "Users can recover access by resetting "
                "their passwords through email."
            ),
            embedding=[
                1.0,
                0.0,
                0.0,
                0.0,
            ],
        ),
        create_chunk(
            chunk_index=2,
            page=3,
            text="The dashboard displays project progress.",
            embedding=[
                0.5,
                0.5,
                0.0,
                0.0,
            ],
        ),
    ]

    ranked = rank_semantic_document_chunks(
        question_embedding=[
            1.0,
            0.0,
            0.0,
            0.0,
        ],
        chunks=chunks,
    )

    assert len(ranked) == 3
    assert ranked[0].chunk.chunk_index == 1
    assert ranked[0].page_start == 2
    assert ranked[0].score == pytest.approx(1.0)


def test_semantic_ranking_respects_limit():
    chunks = [
        create_chunk(
            chunk_index=index,
            page=index + 1,
            text=f"Document information {index}.",
            embedding=[
                1.0,
                float(index),
                0.0,
                0.0,
            ],
        )
        for index in range(4)
    ]

    ranked = rank_semantic_document_chunks(
        question_embedding=[
            1.0,
            0.0,
            0.0,
            0.0,
        ],
        chunks=chunks,
        limit=2,
    )

    assert len(ranked) == 2


def test_chunks_without_valid_embeddings_are_skipped():
    chunks = [
        create_chunk(
            chunk_index=0,
            page=1,
            text="No embedding is available.",
            embedding=None,
        ),
        create_chunk(
            chunk_index=1,
            page=2,
            text="Embedding dimensions do not match.",
            embedding=[
                1.0,
                0.0,
            ],
        ),
        create_chunk(
            chunk_index=2,
            page=3,
            text="This is the valid semantic result.",
            embedding=[
                1.0,
                0.0,
                0.0,
                0.0,
            ],
        ),
    ]

    ranked = rank_semantic_document_chunks(
        question_embedding=[
            1.0,
            0.0,
            0.0,
            0.0,
        ],
        chunks=chunks,
    )

    assert len(ranked) == 1
    assert ranked[0].chunk.chunk_index == 2


def test_semantic_retrieval_returns_document_metadata(
    monkeypatch,
):
    chunks = [
        create_chunk(
            chunk_index=0,
            page=4,
            section_title="Account Recovery",
            text=(
                "Users can reset forgotten passwords "
                "using a secure email link."
            ),
            embedding=[
                1.0,
                0.0,
                0.0,
                0.0,
            ],
        ),
        create_chunk(
            chunk_index=1,
            page=5,
            section_title="Dashboard",
            text="The dashboard shows project analytics.",
            embedding=[
                0.0,
                1.0,
                0.0,
                0.0,
            ],
        ),
    ]

    embedded_document = create_embedded_document(
        chunks
    )

    configuration = create_configuration()

    monkeypatch.setattr(
        semantic_service,
        "ensure_owned_document_embeddings",
        lambda **kwargs: embedded_document,
    )

    monkeypatch.setattr(
        semantic_service,
        "generate_question_embedding",
        lambda **kwargs: (
            [
                1.0,
                0.0,
                0.0,
                0.0,
            ],
            configuration,
        ),
    )

    result = (
        retrieve_owned_document_chunks_semantically(
            document_id=1,
            user_id=1,
            query=(
                "How can a user recover account access?"
            ),
        )
    )

    assert result.document.filename == "requirements.pdf"
    assert result.provider == TEST_PROVIDER
    assert result.model == TEST_MODEL
    assert result.dimensions == TEST_DIMENSIONS

    assert result.chunks[0].page_start == 4

    assert (
        result.chunks[0].section_title
        == "Account Recovery"
    )

    source = result.chunks[0].source()

    assert source["page"] == 4
    assert source["section"] == "Account Recovery"

    assert (
        "password"
        in source["evidence"].lower()
    )


def test_question_and_chunk_configuration_must_match(
    monkeypatch,
):
    chunks = [
        create_chunk(
            chunk_index=0,
            page=1,
            text="Authentication information.",
            embedding=[
                1.0,
                0.0,
                0.0,
                0.0,
            ],
        ),
    ]

    monkeypatch.setattr(
        semantic_service,
        "ensure_owned_document_embeddings",
        lambda **kwargs: create_embedded_document(
            chunks
        ),
    )

    different_configuration = create_configuration(
        model="different-model"
    )

    monkeypatch.setattr(
        semantic_service,
        "generate_question_embedding",
        lambda **kwargs: (
            [
                1.0,
                0.0,
                0.0,
                0.0,
            ],
            different_configuration,
        ),
    )

    with pytest.raises(
        DocumentSemanticRetrievalError,
        match="different configurations",
    ):
        retrieve_owned_document_chunks_semantically(
            document_id=1,
            user_id=1,
            query="What authentication is required?",
        )


def test_empty_semantic_query_is_rejected():
    with pytest.raises(
        DocumentSemanticRetrievalValidationError,
        match="enter a document question",
    ):
        retrieve_owned_document_chunks_semantically(
            document_id=1,
            user_id=1,
            query="   ",
        )


def test_invalid_semantic_result_limit_is_rejected():
    with pytest.raises(
        DocumentSemanticRetrievalValidationError,
        match="cannot exceed",
    ):
        retrieve_owned_document_chunks_semantically(
            document_id=1,
            user_id=1,
            query="Valid question",
            limit=50,
        )


def test_missing_document_error_is_translated(
    monkeypatch,
):
    def fail_embedding(**kwargs):
        raise DocumentEmbeddingNotFoundError(
            "The requested document was not found."
        )

    monkeypatch.setattr(
        semantic_service,
        "ensure_owned_document_embeddings",
        fail_embedding,
    )

    with pytest.raises(
        DocumentSemanticRetrievalNotFoundError,
        match="not found",
    ):
        retrieve_owned_document_chunks_semantically(
            document_id=999,
            user_id=1,
            query="What does the document contain?",
        )


def test_unreadable_document_error_is_translated(
    monkeypatch,
):
    def fail_embedding(**kwargs):
        raise DocumentEmbeddingNotReadyError(
            "This document has no readable extracted text."
        )

    monkeypatch.setattr(
        semantic_service,
        "ensure_owned_document_embeddings",
        fail_embedding,
    )

    with pytest.raises(
        DocumentSemanticRetrievalNotReadyError,
        match="no readable",
    ):
        retrieve_owned_document_chunks_semantically(
            document_id=1,
            user_id=1,
            query="What does the document contain?",
        )
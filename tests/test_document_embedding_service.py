"""Tests for persistent document chunk embeddings."""

import pytest

from database import db
from models import (
    Document,
    DocumentChunk,
    Project,
)
import services.document_embedding_service as embedding_service
from services.document_embedding_service import (
    DocumentEmbeddingConfigurationError,
    DocumentEmbeddingError,
    DocumentEmbeddingNotFoundError,
    DocumentEmbeddingNotReadyError,
    cosine_similarity,
    ensure_owned_document_embeddings,
    get_embedding_configuration,
    normalize_vector,
    prepare_question_for_embedding,
)


TEST_DIMENSIONS = 4


def create_embedding_document(
    *,
    user_id: int,
    extracted_text: str | None,
) -> Document:
    """Create one owned document for embedding tests."""

    project = Project(
        user_id=user_id,
        title="Embedding Test Project",
        status="In Progress",
        priority="High",
    )

    document = Document(
        project=project,
        filename="knowledge.pdf",
        file_path="stored/knowledge.pdf",
        extracted_text=extracted_text,
    )

    db.session.add_all(
        [
            project,
            document,
        ]
    )

    db.session.commit()

    return document


def configure_fake_embedding_environment(
    monkeypatch,
) -> None:
    """Configure embedding settings without using a real provider."""

    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "test-api-key",
    )

    monkeypatch.setenv(
        "GEMINI_EMBEDDING_MODEL",
        "test-embedding-model",
    )

    monkeypatch.setenv(
        "EMBEDDING_DIMENSIONS",
        str(TEST_DIMENSIONS),
    )

    monkeypatch.setattr(
        embedding_service.genai,
        "Client",
        lambda api_key: object(),
    )


def fake_vectors_for_texts(
    *,
    client,
    model,
    dimensions,
    texts,
):
    """Return deterministic vectors without calling Gemini."""

    vectors = []

    for index, _text in enumerate(
        texts
    ):
        vector = [
            0.0
            for _ in range(dimensions)
        ]

        vector[
            index % dimensions
        ] = 1.0

        vectors.append(
            vector
        )

    return vectors


def test_embedding_configuration_reads_environment(
    monkeypatch,
):
    configure_fake_embedding_environment(
        monkeypatch
    )

    configuration = get_embedding_configuration()

    assert configuration.provider == "gemini"

    assert (
        configuration.model
        == "test-embedding-model"
    )

    assert (
        configuration.dimensions
        == TEST_DIMENSIONS
    )

    assert (
        configuration.api_key
        == "test-api-key"
    )


def test_missing_embedding_api_key_is_rejected(
    monkeypatch,
):
    monkeypatch.delenv(
        "GEMINI_API_KEY",
        raising=False,
    )

    monkeypatch.setenv(
        "GEMINI_EMBEDDING_MODEL",
        "test-model",
    )

    monkeypatch.setenv(
        "EMBEDDING_DIMENSIONS",
        "4",
    )

    with pytest.raises(
        DocumentEmbeddingConfigurationError,
        match="GEMINI_API_KEY",
    ):
        get_embedding_configuration()


def test_document_chunks_are_embedded_and_saved(
    app,
    user,
    monkeypatch,
):
    configure_fake_embedding_environment(
        monkeypatch
    )

    monkeypatch.setattr(
        embedding_service,
        "_generate_embeddings",
        fake_vectors_for_texts,
    )

    with app.app_context():
        document = create_embedding_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "Authentication Requirements\n"
                "Users can reset passwords through email.\n\n"
                "--- Page 2 ---\n"
                "Project Dashboard\n"
                "The dashboard displays project progress."
            ),
        )

        result = ensure_owned_document_embeddings(
            document_id=document.id,
            user_id=user,
        )

        assert result.embedded_count == 2
        assert result.reused_count == 0
        assert result.chunks_rebuilt is True

        assert result.provider == "gemini"

        assert (
            result.model
            == "test-embedding-model"
        )

        assert (
            result.dimensions
            == TEST_DIMENSIONS
        )

        chunks = (
            DocumentChunk.query
            .filter_by(
                document_id=document.id,
                user_id=user,
            )
            .order_by(
                DocumentChunk.chunk_index.asc()
            )
            .all()
        )

        assert len(chunks) == 2

        for chunk in chunks:
            assert chunk.has_embedding is True

            assert (
                len(chunk.embedding)
                == TEST_DIMENSIONS
            )

            assert (
                chunk.embedding_provider
                == "gemini"
            )

            assert (
                chunk.embedding_model
                == "test-embedding-model"
            )

            assert (
                chunk.embedding_dimensions
                == TEST_DIMENSIONS
            )

            assert chunk.embedding_fingerprint
            assert chunk.embedded_at is not None


def test_current_embeddings_are_reused(
    app,
    user,
    monkeypatch,
):
    configure_fake_embedding_environment(
        monkeypatch
    )

    call_count = {
        "value": 0,
    }

    def counted_fake_embeddings(**kwargs):
        call_count["value"] += 1

        return fake_vectors_for_texts(
            **kwargs
        )

    monkeypatch.setattr(
        embedding_service,
        "_generate_embeddings",
        counted_fake_embeddings,
    )

    with app.app_context():
        document = create_embedding_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "Authentication Requirements\n"
                "Passwords can be reset through email."
            ),
        )

        first = ensure_owned_document_embeddings(
            document_id=document.id,
            user_id=user,
        )

        second = ensure_owned_document_embeddings(
            document_id=document.id,
            user_id=user,
        )

        assert first.embedded_count == 1
        assert first.reused_count == 0

        assert second.embedded_count == 0
        assert second.reused_count == 1

        assert call_count["value"] == 1


def test_force_regenerates_current_embeddings(
    app,
    user,
    monkeypatch,
):
    configure_fake_embedding_environment(
        monkeypatch
    )

    call_count = {
        "value": 0,
    }

    def counted_fake_embeddings(**kwargs):
        call_count["value"] += 1

        return fake_vectors_for_texts(
            **kwargs
        )

    monkeypatch.setattr(
        embedding_service,
        "_generate_embeddings",
        counted_fake_embeddings,
    )

    with app.app_context():
        document = create_embedding_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "Deployment Requirements\n"
                "The project must be deployed securely."
            ),
        )

        first = ensure_owned_document_embeddings(
            document_id=document.id,
            user_id=user,
        )

        second = ensure_owned_document_embeddings(
            document_id=document.id,
            user_id=user,
            force=True,
        )

        assert first.embedded_count == 1

        assert second.embedded_count == 1
        assert second.reused_count == 0

        assert call_count["value"] == 2


def test_embedding_blocks_other_users(
    app,
    user,
    monkeypatch,
):
    configure_fake_embedding_environment(
        monkeypatch
    )

    monkeypatch.setattr(
        embedding_service,
        "_generate_embeddings",
        fake_vectors_for_texts,
    )

    with app.app_context():
        document = create_embedding_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "Private project information."
            ),
        )

        with pytest.raises(
            DocumentEmbeddingNotFoundError,
            match="not found",
        ):
            ensure_owned_document_embeddings(
                document_id=document.id,
                user_id=user + 9999,
            )


def test_document_without_text_cannot_be_embedded(
    app,
    user,
    monkeypatch,
):
    configure_fake_embedding_environment(
        monkeypatch
    )

    with app.app_context():
        document = create_embedding_document(
            user_id=user,
            extracted_text="",
        )

        with pytest.raises(
            DocumentEmbeddingNotReadyError,
            match="no readable",
        ):
            ensure_owned_document_embeddings(
                document_id=document.id,
                user_id=user,
            )


def test_vector_normalization_and_similarity():
    normalized = normalize_vector(
        [
            3.0,
            4.0,
        ]
    )

    assert normalized[0] == pytest.approx(
        0.6
    )

    assert normalized[1] == pytest.approx(
        0.8
    )

    same_direction = cosine_similarity(
        [
            1.0,
            0.0,
        ],
        [
            5.0,
            0.0,
        ],
    )

    opposite_direction = cosine_similarity(
        [
            1.0,
            0.0,
        ],
        [
            -1.0,
            0.0,
        ],
    )

    assert same_direction == pytest.approx(
        1.0
    )

    assert opposite_direction == pytest.approx(
        -1.0
    )


def test_question_preparation_rejects_empty_question():
    with pytest.raises(
        DocumentEmbeddingError,
        match="Enter a question",
    ):
        prepare_question_for_embedding(
            "   "
        )


def test_provider_failure_does_not_save_partial_embeddings(
    app,
    user,
    monkeypatch,
):
    configure_fake_embedding_environment(
        monkeypatch
    )

    def fail_embedding_request(**kwargs):
        raise RuntimeError(
            "Provider unavailable"
        )

    monkeypatch.setattr(
        embedding_service,
        "_generate_embeddings",
        fail_embedding_request,
    )

    with app.app_context():
        document = create_embedding_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "Authentication information.\n\n"
                "--- Page 2 ---\n"
                "Deployment information."
            ),
        )

        with pytest.raises(
            DocumentEmbeddingError,
            match="provider could not process",
        ):
            ensure_owned_document_embeddings(
                document_id=document.id,
                user_id=user,
            )

        db.session.expire_all()

        chunks = (
            DocumentChunk.query
            .filter_by(
                document_id=document.id,
                user_id=user,
            )
            .all()
        )

        assert len(chunks) == 2

        assert all(
            chunk.has_embedding is False
            for chunk in chunks
        )
        
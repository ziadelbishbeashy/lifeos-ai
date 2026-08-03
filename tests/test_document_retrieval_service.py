"""Tests for Document Brain keyword retrieval."""

import pytest

from database import db
from models import Document, Project
from services.document_retrieval_service import (
    DocumentRetrievalNotFoundError,
    DocumentRetrievalNotReadyError,
    DocumentRetrievalValidationError,
    build_retrieval_context,
    retrieve_owned_document_chunks,
)


def create_retrieval_document(
    *,
    user_id: int,
    extracted_text: str | None,
) -> Document:
    """Create an owned document for retrieval tests."""

    project = Project(
        user_id=user_id,
        title="RAG Retrieval Project",
        status="In Progress",
        priority="High",
    )

    document = Document(
        project=project,
        filename="requirements.pdf",
        file_path="stored/requirements.pdf",
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


def test_retrieval_returns_relevant_page_first(
    app,
    user,
):
    with app.app_context():
        document = create_retrieval_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "Project Overview\n"
                "LifeOS provides project planning, notes "
                "and productivity tools.\n\n"
                "--- Page 2 ---\n"
                "Authentication Requirements\n"
                "The system must support secure login, "
                "email verification and password reset.\n\n"
                "--- Page 3 ---\n"
                "User Interface\n"
                "The dashboard contains responsive cards "
                "and navigation controls."
            ),
        )

        result = retrieve_owned_document_chunks(
            document_id=document.id,
            user_id=user,
            query=(
                "What are the authentication "
                "and password requirements?"
            ),
        )

        assert result.chunks

        assert (
            result.chunks[0].page_start
            == 2
        )

        assert (
            "password"
            in result.chunks[0].matched_terms
        )

        assert result.index_rebuilt is True


def test_retrieval_reuses_current_chunk_index(
    app,
    user,
):
    with app.app_context():
        document = create_retrieval_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "The final report deadline is 20 August."
            ),
        )

        first = retrieve_owned_document_chunks(
            document_id=document.id,
            user_id=user,
            query="What is the report deadline?",
        )

        second = retrieve_owned_document_chunks(
            document_id=document.id,
            user_id=user,
            query="When is the report due?",
        )

        assert first.index_rebuilt is True
        assert second.index_rebuilt is False


def test_retrieval_respects_result_limit(
    app,
    user,
):
    with app.app_context():
        document = create_retrieval_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "Security requirements for login.\n\n"
                "--- Page 2 ---\n"
                "Security requirements for document uploads.\n\n"
                "--- Page 3 ---\n"
                "Security requirements for project ownership."
            ),
        )

        result = retrieve_owned_document_chunks(
            document_id=document.id,
            user_id=user,
            query="security requirements",
            limit=2,
        )

        assert len(result.chunks) == 2


def test_retrieval_blocks_other_users(
    app,
    user,
):
    with app.app_context():
        document = create_retrieval_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "Private project information."
            ),
        )

        with pytest.raises(
            DocumentRetrievalNotFoundError,
            match="not found",
        ):
            retrieve_owned_document_chunks(
                document_id=document.id,
                user_id=user + 9999,
                query="What private information exists?",
            )


def test_document_without_text_is_not_ready(
    app,
    user,
):
    with app.app_context():
        document = create_retrieval_document(
            user_id=user,
            extracted_text="",
        )

        with pytest.raises(
            DocumentRetrievalNotReadyError,
            match="no readable",
        ):
            retrieve_owned_document_chunks(
                document_id=document.id,
                user_id=user,
                query="What does the document say?",
            )


def test_empty_query_is_rejected(
    app,
    user,
):
    with app.app_context():
        document = create_retrieval_document(
            user_id=user,
            extracted_text="Readable text.",
        )

        with pytest.raises(
            DocumentRetrievalValidationError,
            match="enter a document question",
        ):
            retrieve_owned_document_chunks(
                document_id=document.id,
                user_id=user,
                query="   ",
            )


def test_retrieval_context_contains_page_and_text(
    app,
    user,
):
    with app.app_context():
        document = create_retrieval_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "General project introduction.\n\n"
                "--- Page 2 ---\n"
                "The deployment deadline is 10 September."
            ),
        )

        result = retrieve_owned_document_chunks(
            document_id=document.id,
            user_id=user,
            query="deployment deadline",
        )

        context = build_retrieval_context(
            result
        )

        assert "[Source 1" in context
        assert "Page 2" in context
        assert "10 September" in context


def test_source_matches_document_brain_ui_format(
    app,
    user,
):
    with app.app_context():
        document = create_retrieval_document(
            user_id=user,
            extracted_text=(
                "--- Page 4 ---\n"
                "Testing Requirements\n"
                "All authentication tests must pass."
            ),
        )

        result = retrieve_owned_document_chunks(
            document_id=document.id,
            user_id=user,
            query="authentication tests",
        )

        source = result.chunks[0].source()

        assert source["page"] == 4
        assert source["section"]
        assert (
            "authentication"
            in source["evidence"].lower()
        )
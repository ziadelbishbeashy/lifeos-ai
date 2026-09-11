"""Tests for Step 8A source identity and navigation backend."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest

from database import db
from models import (
    Document,
    DocumentChunk,
    Project,
    User,
)
import services.document_question_workflow_service as question_workflow
from services.document_navigation_service import (
    DocumentNavigationNotFoundError,
    get_owned_document_context,
    prepare_owned_document_file,
)
from storage.local import LocalStorage


def create_document_with_chunks(
    *,
    user_id: int,
    filename: str = "navigation.pdf",
    file_path: str = "stored/navigation.pdf",
) -> tuple[Document, list[DocumentChunk]]:
    project = Project(
        user_id=user_id,
        title="Navigation Project",
        status="In Progress",
        priority="Medium",
    )

    document = Document(
        project=project,
        filename=filename,
        file_path=file_path,
        extracted_text=(
            "--- Page 7 ---\nPrevious context.\n"
            "--- Page 8 ---\nSelected context.\n"
            "--- Page 9 ---\nNext context."
        ),
    )

    db.session.add_all(
        [
            project,
            document,
        ]
    )
    db.session.flush()

    chunks = [
        DocumentChunk(
            document_id=document.id,
            user_id=user_id,
            chunk_index=10,
            page_start=7,
            page_end=7,
            section_title="Background",
            text="Previous passage on page seven.",
            character_count=31,
            source_fingerprint="fingerprint",
        ),
        DocumentChunk(
            document_id=document.id,
            user_id=user_id,
            chunk_index=11,
            page_start=8,
            page_end=8,
            section_title="Privacy",
            text="Selected passage on page eight.",
            character_count=31,
            source_fingerprint="fingerprint",
        ),
        DocumentChunk(
            document_id=document.id,
            user_id=user_id,
            chunk_index=12,
            page_start=9,
            page_end=9,
            section_title="Security",
            text="Next passage on page nine.",
            character_count=27,
            source_fingerprint="fingerprint",
        ),
    ]

    db.session.add_all(
        chunks
    )
    db.session.commit()

    return (
        document,
        chunks,
    )


def test_question_sources_save_stable_chunk_identity():
    database_chunk = SimpleNamespace(
        id=57,
        chunk_index=12,
        text=(
            "Every project query verifies ownership before "
            "returning private records."
        ),
    )

    retrieved_source = SimpleNamespace(
        chunk=database_chunk,
        text=database_chunk.text,
        matched_terms=(
            "project",
            "ownership",
        ),
        source=lambda: {
            "page": 8,
            "section": "Privacy",
            "evidence": database_chunk.text,
        },
    )

    retrieval_result = SimpleNamespace(
        query="How is ownership checked?",
        chunks=[
            retrieved_source,
        ],
    )

    sources = question_workflow._sources_from_claims(
        retrieval_result=retrieval_result,
        claims=[
            {
                "text": "Project queries verify ownership.",
                "source_ids": [1],
            }
        ],
    )

    assert sources[0]["source_id"] == 1
    assert sources[0]["chunk_id"] == 57
    assert sources[0]["chunk_index"] == 12
    assert sources[0]["page"] == 8


def test_context_crosses_page_boundaries_but_keeps_page_identity(
    app,
    user,
):
    with app.app_context():
        document, chunks = create_document_with_chunks(
            user_id=user
        )

        result = get_owned_document_context(
            document_id=document.id,
            user_id=user,
            chunk_id=chunks[1].id,
        )

        assert result.previous is not None
        assert result.previous.page_label == "7"
        assert result.current.page_label == "8"
        assert result.next is not None
        assert result.next.page_label == "9"

        assert result.previous.chunk_index == 10
        assert result.current.chunk_index == 11
        assert result.next.chunk_index == 12


def test_context_rejects_chunk_from_another_document(
    app,
    user,
):
    with app.app_context():
        first_document, first_chunks = create_document_with_chunks(
            user_id=user,
            filename="first.pdf",
            file_path="stored/first.pdf",
        )

        second_project = Project(
            user_id=user,
            title="Second Project",
            status="In Progress",
            priority="Medium",
        )

        second_document = Document(
            project=second_project,
            filename="second.pdf",
            file_path="stored/second.pdf",
            extracted_text="Second document.",
        )

        db.session.add_all(
            [
                second_project,
                second_document,
            ]
        )
        db.session.commit()

        with pytest.raises(
            DocumentNavigationNotFoundError
        ):
            get_owned_document_context(
                document_id=second_document.id,
                user_id=user,
                chunk_id=first_chunks[1].id,
            )


def test_context_is_hidden_from_other_user(
    app,
    user,
):
    with app.app_context():
        document, chunks = create_document_with_chunks(
            user_id=user
        )

        other = User(
            name="Other User",
            email="other-navigation@example.com",
        )
        other.set_password(
            "StrongPass123!"
        )
        db.session.add(
            other
        )
        db.session.commit()

        with pytest.raises(
            DocumentNavigationNotFoundError
        ):
            get_owned_document_context(
                document_id=document.id,
                user_id=other.id,
                chunk_id=chunks[1].id,
            )


def test_prepare_owned_document_file_resolves_local_pdf(
    app,
    user,
    tmp_path,
):
    with app.app_context():
        app.config["LOCAL_STORAGE_ROOT"] = str(
            tmp_path
        )

        storage = LocalStorage(
            tmp_path
        )

        storage_key = storage.save(
            BytesIO(
                b"%PDF-1.4\n% LifeOS test PDF\n"
            ),
            original_name="paper.pdf",
            namespace="user-1",
        )

        project = Project(
            user_id=user,
            title="PDF Project",
            status="In Progress",
            priority="Medium",
        )

        document = Document(
            project=project,
            filename="paper.pdf",
            file_path=storage_key,
            extracted_text="Readable text.",
        )

        db.session.add_all(
            [
                project,
                document,
            ]
        )
        db.session.commit()

        result = prepare_owned_document_file(
            document_id=document.id,
            user_id=user,
        )

        assert result.storage_key == storage_key
        assert result.filename == "paper.pdf"
        assert result.local_path is not None
        assert result.local_path.is_file()

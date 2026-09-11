"""Tests for page-aware Document Brain chunking."""

import pytest

from database import db
from models import (
    Document,
    DocumentChunk,
    Project,
)
from services.document_chunk_service import (
    DocumentChunkNotFoundError,
    DocumentChunkNotReadyError,
    build_document_chunks,
    parse_page_blocks,
    rebuild_owned_document_chunks,
    ensure_owned_document_chunks,
)




def create_document(
    *,
    user_id: int,
    extracted_text: str | None,
) -> Document:
    project = Project(
        user_id=user_id,
        title="Chunking Project",
        status="In Progress",
        priority="High",
    )

    document = Document(
        project=project,
        filename="large-document.pdf",
        file_path="stored/large-document.pdf",
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


def test_page_markers_are_parsed():
    pages = parse_page_blocks(
        "--- Page 1 ---\n"
        "First page text.\n\n"
        "--- Page 2 ---\n"
        "Second page text."
    )

    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert pages[0].text == "First page text."
    assert pages[1].page_number == 2


def test_long_page_is_split_with_overlap():
    text = (
        "--- Page 1 ---\n"
        + "LifeOS document knowledge retrieval. " * 100
    )

    chunks = build_document_chunks(
        text,
        max_chars=500,
        overlap_chars=80,
    )

    assert len(chunks) > 1
    assert chunks[0].page_start == 1
    assert chunks[0].chunk_index == 0

    assert all(
        chunk.character_count <= 520
        for chunk in chunks
    )


def test_chunks_are_saved_and_rebuilt(
    app,
    user,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                + "First page content. " * 80
                + "\n--- Page 2 ---\n"
                + "Second page content. " * 80
            ),
        )

        first = rebuild_owned_document_chunks(
            document_id=document.id,
            user_id=user,
            max_chars=500,
            overlap_chars=80,
        )

        assert len(first.chunks) > 2

        first_count = (
            DocumentChunk.query
            .filter_by(
                document_id=document.id
            )
            .count()
        )

        document.extracted_text = (
            "--- Page 1 ---\n"
            "Updated short content."
        )

        db.session.commit()

        second = rebuild_owned_document_chunks(
            document_id=document.id,
            user_id=user,
            max_chars=500,
            overlap_chars=80,
        )

        second_count = (
            DocumentChunk.query
            .filter_by(
                document_id=document.id
            )
            .count()
        )

        assert first_count > 1
        assert second_count == 1
        assert second.chunks[0].chunk_index == 0
        assert "Updated short content" in (
            second.chunks[0].text
        )


def test_other_users_document_is_blocked(
    app,
    user,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable text.",
        )

        with pytest.raises(
            DocumentChunkNotFoundError,
            match="not found",
        ):
            rebuild_owned_document_chunks(
                document_id=document.id,
                user_id=user + 9999,
            )


def test_document_without_text_is_not_ready(
    app,
    user,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="",
        )

        with pytest.raises(
            DocumentChunkNotReadyError,
            match="no readable",
        ):
            rebuild_owned_document_chunks(
                document_id=document.id,
                user_id=user,
            )


def test_invalid_chunk_settings_are_rejected():
    with pytest.raises(
        ValueError,
        match="at least 300",
    ):
        build_document_chunks(
            "Readable text.",
            max_chars=100,
        )

    with pytest.raises(
        ValueError,
        match="smaller than",
    ):
        build_document_chunks(
            "Readable text.",
            max_chars=500,
            overlap_chars=500,
        )

def test_ensure_creates_then_reuses_chunks(
    app,
    user,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                + "Automatic document indexing. " * 80
            ),
        )

        first = ensure_owned_document_chunks(
            document_id=document.id,
            user_id=user,
            max_chars=500,
            overlap_chars=80,
        )

        first_ids = [
            chunk.id
            for chunk in first.chunks
        ]

        second = ensure_owned_document_chunks(
            document_id=document.id,
            user_id=user,
            max_chars=500,
            overlap_chars=80,
        )

        second_ids = [
            chunk.id
            for chunk in second.chunks
        ]

        assert first.rebuilt is True
        assert second.rebuilt is False
        assert first_ids == second_ids
        assert len(second.chunks) > 1


def test_ensure_rebuilds_stale_chunks(
    app,
    user,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "Original authentication requirements."
            ),
        )

        first = ensure_owned_document_chunks(
            document_id=document.id,
            user_id=user,
        )

        old_fingerprint = (
            first.source_fingerprint
        )

        document.extracted_text = (
            "--- Page 1 ---\n"
            "Updated authentication and "
            "email verification requirements."
        )

        db.session.commit()

        second = ensure_owned_document_chunks(
            document_id=document.id,
            user_id=user,
        )

        assert second.rebuilt is True

        assert (
            second.source_fingerprint
            != old_fingerprint
        )

        assert len(second.chunks) == 1

        assert (
            "email verification"
            in second.chunks[0].text
        )
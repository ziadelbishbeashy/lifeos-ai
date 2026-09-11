"""Tests for the Document Brain upload workflow."""

from io import BytesIO

import pytest
from werkzeug.datastructures import FileStorage

from database import db
from models import Document, Project, User
from services.document_access_service import (
    DocumentValidationError,
)
from services.document_service import (
    create_project_pdf_document,
)
from storage.local import LocalStorage


ONE_MEGABYTE = 1024 * 1024


def make_pdf_upload(
    content: bytes = b"%PDF-1.7\nLifeOS PDF content",
    filename: str = "requirements.pdf",
) -> FileStorage:
    """Create an in-memory PDF upload for testing."""

    return FileStorage(
        stream=BytesIO(content),
        filename=filename,
        content_type="application/pdf",
    )


def create_second_user() -> User:
    """Create another user for ownership tests."""

    second_user = User(
        name="Second User",
        email="second-document-user@example.com",
    )
    second_user.set_password("StrongPass123!")

    db.session.add(second_user)
    db.session.commit()

    return second_user


def test_project_pdf_creates_file_and_database_record(
    app,
    user,
    tmp_path,
):
    with app.app_context():
        project = Project(
            user_id=user,
            title="LifeOS",
            status="In Progress",
            priority="High",
        )

        db.session.add(project)
        db.session.commit()

        storage = LocalStorage(tmp_path)
        upload = make_pdf_upload(
            filename="LifeOS Requirements.pdf",
        )

        result = create_project_pdf_document(
            upload,
            owner_id=user,
            project_id=project.id,
            max_bytes=ONE_MEGABYTE,
            storage=storage,
        )

        assert result.document.id is not None
        assert result.document.project_id == project.id
        assert result.document.filename == (
            "LifeOS Requirements.pdf"
        )
        assert result.document.file_path == (
            result.storage_key
        )

        assert result.original_name == (
            "LifeOS Requirements.pdf"
        )
        assert result.safe_name == (
            "LifeOS_Requirements.pdf"
        )

        assert result.storage_key.startswith(
            f"user-{user}-project-{project.id}/"
        )

        assert storage.exists(result.storage_key)

        with storage.open(
            result.storage_key,
            "rb",
        ) as stored_file:
            assert stored_file.read() == (
                b"%PDF-1.7\nLifeOS PDF content"
            )

        saved_document = db.session.get(
            Document,
            result.document.id,
        )

        assert saved_document is not None
        assert saved_document.filename == (
            "LifeOS Requirements.pdf"
        )
        assert Document.query.count() == 1


def test_upload_to_another_users_project_is_blocked_and_cleaned_up(
    app,
    user,
    tmp_path,
):
    with app.app_context():
        second_user = create_second_user()

        private_project = Project(
            user_id=second_user.id,
            title="Private Project",
            status="In Progress",
            priority="Medium",
        )

        db.session.add(private_project)
        db.session.commit()

        storage = LocalStorage(tmp_path)
        upload = make_pdf_upload(
            filename="private.pdf",
        )

        with pytest.raises(
            DocumentValidationError,
            match="Select a project from your workspace",
        ):
            create_project_pdf_document(
                upload,
                owner_id=user,
                project_id=private_project.id,
                max_bytes=ONE_MEGABYTE,
                storage=storage,
            )

        assert Document.query.count() == 0

        stored_files = [
            path
            for path in tmp_path.rglob("*")
            if path.is_file()
        ]

        assert stored_files == []
"""Ownership-safe access boundary for LifeOS documents.

Documents are owned directly by a user. ``project_id`` is an optional workspace
association rather than the ownership boundary, which lets the same Document
Brain pipeline support Projects, Modules, Collections, and general documents.
"""

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import Document, Project


class DocumentNotFoundError(LookupError):
    """Raised when a document is not visible to the requested user."""


class DocumentValidationError(ValueError):
    """Raised when document metadata is unsafe or incomplete."""


class DocumentPersistenceError(RuntimeError):
    """Raised when document metadata cannot be persisted."""


def list_owned_documents(owner_id: int) -> list[Document]:
    return (
        Document.query
        .filter(Document.user_id == owner_id)
        .order_by(Document.uploaded_at.desc(), Document.id.desc())
        .all()
    )


def require_owned_document(document_id: int, owner_id: int) -> Document:
    document = Document.query.filter_by(id=document_id, user_id=owner_id).first()
    if document is None:
        raise DocumentNotFoundError
    return document


def create_document_metadata(
    *,
    owner_id: int,
    filename: str,
    storage_key: str,
    project_id: int | None = None,
) -> Document:
    """Create user-owned document metadata with an optional project link."""

    if owner_id <= 0:
        raise DocumentValidationError("A valid document owner is required.")

    if project_id is not None:
        project = Project.query.filter_by(id=project_id, user_id=owner_id).first()
        if project is None:
            raise DocumentValidationError("Select a project from your workspace.")

    filename = (filename or "").strip()
    storage_key = (storage_key or "").strip()
    if not filename or not storage_key:
        raise DocumentValidationError("Document filename and storage key are required.")

    document = Document(
        user_id=owner_id,
        project_id=project_id,
        filename=filename[:255],
        file_path=storage_key[:500],
    )
    try:
        db.session.add(document)
        db.session.commit()
        return document
    except SQLAlchemyError as error:
        db.session.rollback()
        raise DocumentPersistenceError from error


def create_legacy_document_metadata(
    *,
    owner_id: int,
    project_id: int,
    filename: str,
    storage_key: str,
) -> Document:
    """Backward-compatible project upload entry point."""

    return create_document_metadata(
        owner_id=owner_id,
        project_id=project_id,
        filename=filename,
        storage_key=storage_key,
    )

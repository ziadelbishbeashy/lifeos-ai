"""Ownership-safe access boundary for the legacy Document model.

Document Brain is not implemented yet. Until its future schema migration adds a
direct owner field, documents are considered owned only through an owned
project. General documents must not be created with the legacy model.
"""

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import Document, Project


class DocumentNotFoundError(LookupError):
    """Raised when a document is not visible to the requested user."""


class DocumentValidationError(ValueError):
    """Raised when legacy document metadata is unsafe or incomplete."""


class DocumentPersistenceError(RuntimeError):
    """Raised when document metadata cannot be persisted."""


def list_owned_documents(owner_id: int) -> list[Document]:
    return (
        Document.query.join(Project, Document.project_id == Project.id)
        .filter(Project.user_id == owner_id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )


def require_owned_document(document_id: int, owner_id: int) -> Document:
    document = (
        Document.query.join(Project, Document.project_id == Project.id)
        .filter(Document.id == document_id, Project.user_id == owner_id)
        .first()
    )
    if document is None:
        raise DocumentNotFoundError
    return document


def create_legacy_document_metadata(
    *,
    owner_id: int,
    project_id: int,
    filename: str,
    storage_key: str,
) -> Document:
    project = Project.query.filter_by(id=project_id, user_id=owner_id).first()
    if project is None:
        raise DocumentValidationError("Select a project from your workspace.")
    filename = (filename or "").strip()
    storage_key = (storage_key or "").strip()
    if not filename or not storage_key:
        raise DocumentValidationError("Document filename and storage key are required.")

    document = Document(
        project_id=project.id,
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

"""Document Brain upload, extraction and indexing workflow."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError
from werkzeug.datastructures import FileStorage

from database import db
from models import Document
from services.document_access_service import (
    DocumentPersistenceError,
    DocumentValidationError,
    create_legacy_document_metadata,
)
from services.document_chunk_service import (
    DocumentChunkError,
    ensure_owned_document_chunks,
)
from services.pdf_service import (
    PDFExtractionError,
    StoredPDF,
    extract_pdf_text,
    store_pdf_upload,
)
from storage.base import StorageError, StorageService
from storage.service import get_storage


class DocumentUploadError(RuntimeError):
    """Raised when a document upload cannot be completed safely."""


@dataclass(frozen=True)
class CreatedProjectDocument:
    """Result of storing and processing a project PDF."""

    document: Document
    original_name: str
    safe_name: str
    size_bytes: int
    storage_key: str

    extraction_succeeded: bool
    page_count: int
    pages_with_text: int
    extracted_characters: int
    extraction_message: str | None

    indexing_succeeded: bool = False
    chunk_count: int = 0
    indexing_message: str | None = None


def create_project_pdf_document(
    upload: FileStorage | None,
    *,
    owner_id: int,
    project_id: int,
    max_bytes: int,
    storage: StorageService | None = None,
) -> CreatedProjectDocument:
    """
    Store a PDF, create its database record, extract text and
    automatically prepare searchable chunks.
    """

    storage_service = storage or get_storage()

    stored_pdf = store_pdf_upload(
        upload,
        owner_id=owner_id,
        project_id=project_id,
        max_bytes=max_bytes,
        storage=storage_service,
    )

    try:
        document = create_legacy_document_metadata(
            owner_id=owner_id,
            project_id=project_id,
            filename=stored_pdf.original_name,
            storage_key=stored_pdf.storage_key,
        )

    except (
        DocumentValidationError,
        DocumentPersistenceError,
    ):
        _delete_failed_upload(
            storage=storage_service,
            stored_pdf=stored_pdf,
        )

        raise

    try:
        extraction = extract_pdf_text(
            stored_pdf.storage_key,
            storage=storage_service,
        )

    except PDFExtractionError as error:
        # Keep the uploaded PDF. It may require OCR or
        # a later text-extraction retry.
        return CreatedProjectDocument(
            document=document,
            original_name=stored_pdf.original_name,
            safe_name=stored_pdf.safe_name,
            size_bytes=stored_pdf.size_bytes,
            storage_key=stored_pdf.storage_key,
            extraction_succeeded=False,
            page_count=0,
            pages_with_text=0,
            extracted_characters=0,
            extraction_message=str(error),
            indexing_succeeded=False,
            chunk_count=0,
            indexing_message=(
                "Chunk indexing was skipped because text "
                "extraction did not complete."
            ),
        )

    extracted_text = str(
        extraction.text or ""
    )

    try:
        document.extracted_text = extracted_text
        db.session.commit()

    except SQLAlchemyError as error:
        db.session.rollback()

        raise DocumentUploadError(
            "The PDF was uploaded, but its extracted text "
            "could not be saved."
        ) from error

    # A successful PDF extraction can still return no readable text,
    # particularly for scanned image-only PDFs.
    if not extracted_text.strip():
        return CreatedProjectDocument(
            document=document,
            original_name=stored_pdf.original_name,
            safe_name=stored_pdf.safe_name,
            size_bytes=stored_pdf.size_bytes,
            storage_key=stored_pdf.storage_key,
            extraction_succeeded=True,
            page_count=extraction.page_count,
            pages_with_text=extraction.pages_with_text,
            extracted_characters=0,
            extraction_message=None,
            indexing_succeeded=False,
            chunk_count=0,
            indexing_message=(
                "No readable text was available for indexing."
            ),
        )

    try:
        chunk_result = ensure_owned_document_chunks(
            document_id=document.id,
            user_id=owner_id,
        )

    except DocumentChunkError as error:
        # Keep the uploaded document and extracted text.
        # Indexing can safely be retried later.
        return CreatedProjectDocument(
            document=document,
            original_name=stored_pdf.original_name,
            safe_name=stored_pdf.safe_name,
            size_bytes=stored_pdf.size_bytes,
            storage_key=stored_pdf.storage_key,
            extraction_succeeded=True,
            page_count=extraction.page_count,
            pages_with_text=extraction.pages_with_text,
            extracted_characters=len(extracted_text),
            extraction_message=None,
            indexing_succeeded=False,
            chunk_count=0,
            indexing_message=str(error),
        )

    return CreatedProjectDocument(
        document=document,
        original_name=stored_pdf.original_name,
        safe_name=stored_pdf.safe_name,
        size_bytes=stored_pdf.size_bytes,
        storage_key=stored_pdf.storage_key,
        extraction_succeeded=True,
        page_count=extraction.page_count,
        pages_with_text=extraction.pages_with_text,
        extracted_characters=len(extracted_text),
        extraction_message=None,
        indexing_succeeded=True,
        chunk_count=len(chunk_result.chunks),
        indexing_message=None,
    )


def _delete_failed_upload(
    *,
    storage: StorageService,
    stored_pdf: StoredPDF,
) -> None:
    """Delete a file when its database record cannot be created."""

    try:
        storage.delete(
            stored_pdf.storage_key
        )

    except StorageError as error:
        raise DocumentUploadError(
            "The document record could not be created, and LifeOS "
            "could not remove the stored file."
        ) from error
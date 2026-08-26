"""Authoritative OCR workflow for owned Document Brain PDFs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from database import db
from jobs.base import JobExecutionError
from jobs.queue import JobQueue
from jobs.service import get_job_queue
from models import Document
from ocr.base import OCRConfigurationError, OCRProvider
from ocr.service import get_ocr_provider
from ocr.preprocessing import OCRPreprocessingError, preprocess_ocr_image
from services.document_access_service import DocumentNotFoundError, require_owned_document
from services.document_chunk_service import DocumentChunkError, ensure_owned_document_chunks
from services.document_ocr_service import DocumentOCRError, OCRDocumentExtraction, extract_stored_pdf_with_ocr
from storage.base import StorageService
from storage.service import get_storage


OCR_JOB_NAME = "document.ocr"
ACTIVE_OCR_STATUSES = {"queued", "processing"}


class DocumentOCRWorkflowError(RuntimeError):
    """Base workflow error for OCR operations."""


class DocumentOCRNotFoundError(DocumentOCRWorkflowError):
    """Raised when an OCR request targets another user's or missing document."""


class DocumentOCRNotReadyError(DocumentOCRWorkflowError):
    """Raised when OCR cannot be started for the document."""


@dataclass(frozen=True)
class QueuedDocumentOCR:
    document: Document
    job_id: str | None
    queued: bool


@dataclass(frozen=True)
class ProcessedDocumentOCR:
    document: Document
    extraction: OCRDocumentExtraction
    indexing_succeeded: bool
    chunk_count: int
    indexing_message: str | None


def queue_owned_document_ocr(
    *,
    document_id: int,
    user_id: int,
    force: bool = False,
    queue: JobQueue | None = None,
) -> QueuedDocumentOCR:
    document = _require_document(document_id=document_id, user_id=user_id)

    if document.ocr_status in ACTIVE_OCR_STATUSES and not force:
        return QueuedDocumentOCR(document=document, job_id=None, queued=False)

    if document.ocr_status == "not_needed" and not force:
        return QueuedDocumentOCR(document=document, job_id=None, queued=False)

    document.ocr_status = "queued"
    document.ocr_error = None
    document.ocr_completed_at = None
    document.ocr_pages_processed = 0

    try:
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise DocumentOCRWorkflowError(
            "LifeOS could not queue OCR for this document."
        ) from error

    job_queue = queue or get_job_queue()

    try:
        job = job_queue.enqueue(
            OCR_JOB_NAME,
            {
                "document_id": document.id,
                "user_id": user_id,
            },
        )
    except JobExecutionError as error:
        _mark_failed(
            document_id=document.id,
            message="LifeOS could not start the OCR job.",
        )
        raise DocumentOCRWorkflowError(
            "LifeOS could not start OCR for this document."
        ) from error

    # Inline development jobs may already have completed; refresh the ORM row.
    db.session.expire_all()
    refreshed = db.session.get(Document, document.id) or document

    return QueuedDocumentOCR(
        document=refreshed,
        job_id=job.id,
        queued=True,
    )


def process_owned_document_ocr(
    *,
    document_id: int,
    user_id: int,
    provider: OCRProvider | None = None,
    storage: StorageService | None = None,
    render_page=None,
) -> ProcessedDocumentOCR:
    document = _require_document(document_id=document_id, user_id=user_id)

    document.ocr_status = "processing"
    document.ocr_started_at = datetime.utcnow()
    document.ocr_completed_at = None
    document.ocr_error = None
    document.ocr_pages_processed = 0

    try:
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise DocumentOCRWorkflowError(
            "LifeOS could not start OCR processing."
        ) from error

    try:
        active_provider = provider or get_ocr_provider()
        storage_service = storage or get_storage()
        kwargs = {
            "provider": active_provider,
            "storage": storage_service,
            "render_dpi": int(current_app.config.get("OCR_RENDER_DPI", 300)),
            "low_confidence_threshold": float(
                current_app.config.get("OCR_LOW_CONFIDENCE_THRESHOLD", 0.70)
            ),
        }
        if render_page is not None:
            kwargs["render_page"] = render_page

        if bool(current_app.config.get("OCR_PREPROCESSING_ENABLED", False)):
            preprocessing_mode = str(
                current_app.config.get("OCR_PREPROCESSING_MODE", "auto") or "auto"
            ).strip().lower()

            def preprocess_image(image_bytes: bytes) -> bytes:
                return preprocess_ocr_image(
                    image_bytes,
                    mode=preprocessing_mode,
                ).image_bytes

            kwargs["preprocess_image"] = preprocess_image

        extraction = extract_stored_pdf_with_ocr(
            document.file_path,
            **kwargs,
        )

        document.extracted_text = extraction.text
        document.ocr_status = "completed"
        document.ocr_provider = active_provider.name
        document.ocr_total_pages = extraction.page_count
        document.ocr_pages_requested = extraction.ocr_page_count
        document.ocr_pages_processed = extraction.pages_processed
        document.ocr_low_confidence_pages = extraction.low_confidence_page_count
        document.ocr_average_confidence = extraction.average_confidence
        document.ocr_completed_at = datetime.utcnow()
        document.ocr_error = None
        document.ocr_layout_json = json.dumps(
            {
                "version": 1,
                "pages": {
                    str(page.page_number): {
                        "page": page.page_number,
                        "source": page.source,
                        "confidence": page.confidence,
                        "text": page.text,
                        "words": [
                            {
                                "text": word.text,
                                "left": round(float(word.left), 7),
                                "top": round(float(word.top), 7),
                                "width": round(float(word.width), 7),
                                "height": round(float(word.height), 7),
                                "confidence": (
                                    round(float(word.confidence), 4)
                                    if word.confidence is not None
                                    else None
                                ),
                            }
                            for word in page.words
                        ],
                    }
                    for page in extraction.pages
                    if page.source == "ocr"
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

        db.session.commit()

    except (DocumentOCRError, OCRConfigurationError, OCRPreprocessingError, ValueError) as error:
        db.session.rollback()
        _mark_failed(document_id=document.id, message=str(error))
        raise DocumentOCRWorkflowError(str(error)) from error
    except SQLAlchemyError as error:
        db.session.rollback()
        _mark_failed(
            document_id=document.id,
            message="LifeOS could not save the OCR result.",
        )
        raise DocumentOCRWorkflowError(
            "LifeOS could not save the OCR result."
        ) from error

    indexing_succeeded = False
    chunk_count = 0
    indexing_message: str | None = None

    if extraction.text.strip():
        try:
            chunk_result = ensure_owned_document_chunks(
                document_id=document.id,
                user_id=user_id,
            )
            indexing_succeeded = True
            chunk_count = len(chunk_result.chunks)
        except DocumentChunkError as error:
            # OCR is still a success. Search/indexing can be retried independently.
            indexing_message = str(error)
    else:
        indexing_message = "OCR completed but no readable text was found."

    db.session.expire_all()
    refreshed = db.session.get(Document, document.id) or document

    return ProcessedDocumentOCR(
        document=refreshed,
        extraction=extraction,
        indexing_succeeded=indexing_succeeded,
        chunk_count=chunk_count,
        indexing_message=indexing_message,
    )


def _require_document(*, document_id: int, user_id: int) -> Document:
    try:
        return require_owned_document(document_id=document_id, owner_id=user_id)
    except DocumentNotFoundError as error:
        raise DocumentOCRNotFoundError(
            "The requested document was not found."
        ) from error


def _mark_failed(*, document_id: int, message: str) -> None:
    try:
        document = db.session.get(Document, document_id)
        if document is None:
            return
        document.ocr_status = "failed"
        document.ocr_error = str(message or "OCR failed.")[:4000]
        document.ocr_completed_at = datetime.utcnow()
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()

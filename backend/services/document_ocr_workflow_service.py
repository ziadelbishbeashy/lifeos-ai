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
from ocr.quality import classify_ocr_quality
from ocr.service import get_ocr_provider
from ocr.preprocessing import OCRPreprocessingError, OCRPreprocessingResult, preprocess_ocr_image
from services.document_access_service import DocumentNotFoundError, require_owned_document
from services.document_chunk_service import (
    DocumentChunkError,
    ensure_owned_document_chunks,
    rebuild_owned_document_chunks,
)
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

    _log_ocr_event(
        "ocr_run_started",
        document_id=document.id,
        user_id=user_id,
        force=force,
        stage="queued",
    )

    try:
        job = job_queue.enqueue(
            OCR_JOB_NAME,
            {
                "document_id": document.id,
                "user_id": user_id,
                "force": force,
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
    force: bool = False,
    provider: OCRProvider | None = None,
    storage: StorageService | None = None,
    render_page=None,
) -> ProcessedDocumentOCR:
    document = _require_document(document_id=document_id, user_id=user_id)
    previous_text = str(document.extracted_text or "")

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

    _log_ocr_event(
        "ocr_processing_started",
        document_id=document.id,
        user_id=user_id,
        force=force,
    )

    preprocessing_results: list[OCRPreprocessingResult] = []
    preprocessing_mode = "none"

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
                result = preprocess_ocr_image(
                    image_bytes,
                    mode=preprocessing_mode,
                )
                preprocessing_results.append(result)
                return result.image_bytes

            kwargs["preprocess_image"] = preprocess_image

        extraction = extract_stored_pdf_with_ocr(
            document.file_path,
            **kwargs,
        )

        ocr_preprocessing = iter(preprocessing_results)
        page_preprocessing: dict[int, OCRPreprocessingResult | None] = {}
        for page in extraction.pages:
            if page.source == "ocr":
                page_preprocessing[page.page_number] = next(ocr_preprocessing, None)

        for page in extraction.pages:
            page_confidence = page.confidence if page.source == "ocr" else None
            page_quality = classify_ocr_quality(
                character_count=page.character_count,
                word_count=page.word_count,
                average_confidence=page_confidence,
            )
            if page.source == "ocr":
                audit = page_preprocessing.get(page.page_number)
                operations = tuple(audit.operations) if audit is not None else ()
                _log_ocr_event(
                    "page_ocr_completed",
                    document_id=document.id,
                    page_number=page.page_number,
                    ocr_reason=page.ocr_reason,
                    character_count=page.character_count,
                    word_count=page.word_count,
                    confidence=page.confidence,
                    quality=page_quality,
                    selected_provider=page.provider_name or active_provider.name,
                    selected_strategy=page.provider_strategy,
                    provider_attempts=[
                        {
                            "provider": attempt.provider,
                            "strategy": attempt.strategy,
                            "quality": attempt.quality,
                            "character_count": attempt.character_count,
                            "word_count": attempt.word_count,
                            "confidence": attempt.confidence,
                            "score": attempt.score,
                            "error": attempt.error,
                        }
                        for attempt in page.attempts
                    ],
                    preprocessing_used=bool(audit is not None),
                    preprocessing_mode=preprocessing_mode,
                    preprocessing_operations=list(operations),
                    deskew_angle=(audit.estimated_skew_degrees if audit is not None else None),
                    contrast_adjusted="clahe_contrast" in operations,
                    threshold_applied="otsu_threshold" in operations,
                )
            else:
                _log_ocr_event(
                    "page_native_kept",
                    document_id=document.id,
                    page_number=page.page_number,
                    character_count=page.character_count,
                    word_count=page.word_count,
                    quality=page_quality,
                )

        document_quality = classify_ocr_quality(
            character_count=extraction.total_character_count,
            word_count=extraction.total_word_count,
            average_confidence=extraction.average_confidence,
            page_count=extraction.page_count,
        )

        selected_provider_names = {
            str(page.provider_name or "").strip()
            for page in extraction.pages
            if page.source == "ocr" and str(page.provider_name or "").strip()
        }
        document_provider_name = (
            next(iter(selected_provider_names))
            if len(selected_provider_names) == 1
            else ("adaptive" if selected_provider_names else active_provider.name)
        )

        document.extracted_text = extraction.text
        document.ocr_status = "completed"
        document.ocr_provider = document_provider_name
        document.ocr_total_pages = extraction.page_count
        document.ocr_pages_requested = extraction.ocr_page_count
        document.ocr_pages_processed = extraction.pages_processed
        document.ocr_low_confidence_pages = extraction.low_confidence_page_count
        document.ocr_average_confidence = extraction.average_confidence
        document.ocr_total_characters = extraction.total_character_count
        document.ocr_total_words = extraction.total_word_count
        document.ocr_quality = document_quality
        document.ocr_completed_at = datetime.utcnow()
        document.ocr_error = None
        document.ocr_layout_json = json.dumps(
            {
                "version": 2,
                "metadata": {
                    "provider": active_provider.name,
                    "preprocessing_mode": preprocessing_mode,
                    "tesseract_psm_modes": current_app.config.get("OCR_TESSERACT_PSM_MODES", "3,6,11"),
                    "easyocr_enabled": bool(current_app.config.get("OCR_EASYOCR_ENABLED", False)),
                    "total_characters": extraction.total_character_count,
                    "total_words": extraction.total_word_count,
                    "quality": document_quality,
                },
                "pages": {
                    str(page.page_number): _serialize_ocr_layout_page(
                        page=page,
                        preprocessing=page_preprocessing.get(page.page_number),
                        preprocessing_mode=preprocessing_mode,
                    )
                    for page in extraction.pages
                    if page.source == "ocr"
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

        db.session.commit()

        _log_ocr_event(
            "document_text_replaced",
            document_id=document.id,
            force=force,
            changed=previous_text != extraction.text,
            previous_character_count=len(previous_text),
            new_character_count=len(extraction.text),
        )
        _log_ocr_event(
            "ocr_run_completed",
            document_id=document.id,
            provider=document_provider_name,
            engine=active_provider.name,
            preprocessing_mode=preprocessing_mode,
            total_pages=extraction.page_count,
            pages_requested=extraction.ocr_page_count,
            pages_processed=extraction.pages_processed,
            total_characters=extraction.total_character_count,
            total_words=extraction.total_word_count,
            average_confidence=extraction.average_confidence,
            quality=document_quality,
            force=force,
        )

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
            if force:
                _log_ocr_event(
                    "chunks_invalidated",
                    document_id=document.id,
                    reason="forced_ocr_rerun",
                )
                chunk_result = rebuild_owned_document_chunks(
                    document_id=document.id,
                    user_id=user_id,
                )
                chunks_rebuilt = True
            else:
                chunk_result = ensure_owned_document_chunks(
                    document_id=document.id,
                    user_id=user_id,
                )
                chunks_rebuilt = bool(getattr(chunk_result, "rebuilt", False))

            indexing_succeeded = True
            chunk_count = len(chunk_result.chunks)
            _log_ocr_event(
                "chunks_rebuilt",
                document_id=document.id,
                rebuilt=chunks_rebuilt,
                force=force,
                chunk_count=chunk_count,
                source_fingerprint=getattr(chunk_result, "source_fingerprint", None),
            )

            # Embeddings live on DocumentChunk rows. A hard/new chunk rebuild
            # therefore invalidates old semantic vectors automatically. They are
            # regenerated lazily by the existing semantic retrieval service on
            # the next search/question; we log that truth rather than calling a
            # live embedding provider from the OCR transaction.
            if chunks_rebuilt:
                _log_ocr_event(
                    "embeddings_rebuilt",
                    document_id=document.id,
                    performed=False,
                    reason="chunk_rows_rebuilt; regeneration_deferred_to_semantic_retrieval",
                )
            else:
                _log_ocr_event(
                    "embeddings_reused",
                    document_id=document.id,
                    reason="chunk_source_fingerprint_unchanged",
                )

            _log_ocr_event(
                "index_rebuilt",
                document_id=document.id,
                keyword_index_rebuilt=chunks_rebuilt,
                semantic_index_rebuild_deferred=chunks_rebuilt,
                chunk_count=chunk_count,
            )
        except DocumentChunkError as error:
            # OCR is still a success. Search/indexing can be retried independently.
            indexing_message = str(error)
            _log_ocr_event(
                "index_rebuilt",
                document_id=document.id,
                success=False,
                error=str(error),
            )
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


def _serialize_ocr_layout_page(*, page, preprocessing, preprocessing_mode: str) -> dict:
    confidence = page.confidence if page.source == "ocr" else None
    quality = classify_ocr_quality(
        character_count=page.character_count,
        word_count=page.word_count,
        average_confidence=confidence,
    )
    operations = tuple(preprocessing.operations) if preprocessing is not None else ()
    return {
        "page": page.page_number,
        "source": page.source,
        "confidence": page.confidence,
        "quality": quality,
        "ocr_reason": page.ocr_reason,
        "character_count": page.character_count,
        "word_count": page.word_count,
        "text": page.text,
        "selected_provider": page.provider_name,
        "selected_strategy": page.provider_strategy,
        "selection_attempts": [
            {
                "provider": attempt.provider,
                "strategy": attempt.strategy,
                "quality": attempt.quality,
                "character_count": attempt.character_count,
                "word_count": attempt.word_count,
                "confidence": attempt.confidence,
                "score": attempt.score,
                "error": attempt.error,
            }
            for attempt in page.attempts
        ],
        "preprocessing": {
            "used": bool(preprocessing is not None),
            "mode": preprocessing_mode,
            "operations": list(operations),
            "deskew_angle": (
                preprocessing.estimated_skew_degrees if preprocessing is not None else None
            ),
            "contrast_adjusted": "clahe_contrast" in operations,
            "threshold_applied": "otsu_threshold" in operations,
        },
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
        _log_ocr_event(
            "ocr_run_failed",
            document_id=document_id,
            error=document.ocr_error,
        )
    except SQLAlchemyError:
        db.session.rollback()


def _log_ocr_event(event: str, **fields) -> None:
    payload = {"event": event, **fields}
    current_app.logger.info(
        "lifeos.document_ocr %s",
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
    )

"""Ownership-aware workflow for Document Brain type detection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import Document
from services.ai_operation_lock_service import (
    AIOperationAlreadyRunningError,
    ai_operation_lock,
)
from services.document_type_detection_service import (
    DocumentTypeDetectionError,
    DocumentTypeDetectionResult,
    detect_document_type,
)


DOCUMENT_TYPE_DETECTION_CACHE_VERSION = "document-type-detection-v2"
DOCUMENT_TYPE_DETECTION_OPERATION = "document_type_detection"


class DocumentTypeDetectionWorkflowError(RuntimeError):
    """Raised when owned-document type detection cannot be completed."""


class DocumentTypeDetectionNotFoundError(DocumentTypeDetectionWorkflowError):
    """Raised when the document does not exist or is not owned."""


class DocumentTypeDetectionNotReadyError(DocumentTypeDetectionWorkflowError):
    """Raised when the document has no readable text."""


class DocumentTypeDetectionInProgressError(DocumentTypeDetectionWorkflowError):
    """Raised when the same document is already being classified."""


@dataclass(frozen=True)
class OwnedDocumentTypeDetection:
    """Type detection result tied to the owned document."""

    document: Document
    detection: DocumentTypeDetectionResult
    reused_existing: bool = False


def create_document_type_detection_fingerprint(*, filename: str, extracted_text: str) -> str:
    """Fingerprint the exact source and detector contract used by the cache."""

    fingerprint_input = "\n".join(
        [
            DOCUMENT_TYPE_DETECTION_CACHE_VERSION,
            str(filename or "").strip(),
            str(extracted_text or "").strip(),
        ]
    )
    return hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()


def _cached_detection(document: Document, *, fingerprint: str) -> DocumentTypeDetectionResult | None:
    if str(document.type_detection_fingerprint or "") != fingerprint:
        return None
    raw = str(document.type_detection_cache_json or "").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return None
        return DocumentTypeDetectionResult(
            document_type_key=str(payload["document_type_key"]),
            document_type_label=str(payload["document_type_label"]),
            confidence=str(payload["confidence"]),
            reason=str(payload["reason"]),
            provider=str(payload.get("provider") or "cached"),
            model=str(payload.get("model") or "cached"),
            sampled_characters=max(0, int(payload.get("sampled_characters") or 0)),
            document_characters=max(0, int(payload.get("document_characters") or 0)),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _save_detection_cache(
    document: Document,
    *,
    fingerprint: str,
    detection: DocumentTypeDetectionResult,
) -> None:
    """Persist a non-authoritative cache of the proposal shown for confirmation."""

    document.type_detection_fingerprint = fingerprint
    document.type_detection_cache_json = json.dumps(asdict(detection), ensure_ascii=False)
    document.type_detection_updated_at = datetime.utcnow()
    try:
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        # A cache failure must not cause a paid successful detection to look failed.
        # Return the result; the next request may simply classify again.
        return


def detect_owned_document_type(
    *,
    document_id: int,
    user_id: int,
    force: bool = False,
) -> OwnedDocumentTypeDetection:
    """Detect an owned document's type without saving full analysis.

    Repeated requests for unchanged content reuse the saved proposal. Concurrent
    duplicate requests are rejected before another provider call is started.
    """

    document = _find_owned_document(document_id=document_id, user_id=user_id)
    if document is None:
        raise DocumentTypeDetectionNotFoundError("The requested document was not found.")

    extracted_text = str(document.extracted_text or "").strip()
    if not extracted_text:
        raise DocumentTypeDetectionNotReadyError(
            "This document has no readable extracted text. It may require OCR before type detection."
        )

    fingerprint = create_document_type_detection_fingerprint(
        filename=document.filename,
        extracted_text=extracted_text,
    )

    if not force:
        cached = _cached_detection(document, fingerprint=fingerprint)
        if cached is not None:
            return OwnedDocumentTypeDetection(document=document, detection=cached, reused_existing=True)

    try:
        with ai_operation_lock(
            user_id=user_id,
            operation=DOCUMENT_TYPE_DETECTION_OPERATION,
            resource_type="document",
            resource_id=document.id,
            fingerprint=fingerprint,
            ttl_seconds=180,
        ):
            # Re-read after acquiring the lock so a request that completed just
            # before us can be reused instead of paying for another classification.
            db.session.expire(document)
            document = _find_owned_document(document_id=document_id, user_id=user_id) or document
            if not force:
                cached = _cached_detection(document, fingerprint=fingerprint)
                if cached is not None:
                    return OwnedDocumentTypeDetection(document=document, detection=cached, reused_existing=True)

            try:
                detection = detect_document_type(
                    filename=document.filename,
                    extracted_text=extracted_text,
                )
            except DocumentTypeDetectionError as error:
                raise DocumentTypeDetectionWorkflowError(str(error)) from error

            _save_detection_cache(document, fingerprint=fingerprint, detection=detection)
            return OwnedDocumentTypeDetection(document=document, detection=detection, reused_existing=False)
    except AIOperationAlreadyRunningError as error:
        raise DocumentTypeDetectionInProgressError(
            "This document is already being checked. Please wait for the current detection to finish."
        ) from error


def _find_owned_document(*, document_id: int, user_id: int) -> Document | None:
    return (
        Document.query
        .filter(Document.id == document_id, Document.user_id == user_id)
        .first()
    )

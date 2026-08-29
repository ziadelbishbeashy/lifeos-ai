"""Ownership-aware workflow for Document Brain type detection."""

from __future__ import annotations

from dataclasses import dataclass

from models import (
    Document,
    Project,
)
from services.document_type_detection_service import (
    DocumentTypeDetectionError,
    DocumentTypeDetectionResult,
    detect_document_type,
)


class DocumentTypeDetectionWorkflowError(RuntimeError):
    """Raised when owned-document type detection cannot be completed."""


class DocumentTypeDetectionNotFoundError(
    DocumentTypeDetectionWorkflowError
):
    """Raised when the document does not exist or is not owned."""


class DocumentTypeDetectionNotReadyError(
    DocumentTypeDetectionWorkflowError
):
    """Raised when the document has no readable text."""


@dataclass(frozen=True)
class OwnedDocumentTypeDetection:
    """Type detection result tied to the owned document."""

    document: Document
    detection: DocumentTypeDetectionResult


def detect_owned_document_type(
    *,
    document_id: int,
    user_id: int,
) -> OwnedDocumentTypeDetection:
    """
    Detect an owned document's type without saving full analysis.

    Step 6C will use this result to show the detected type and let the
    user confirm or change it before full analysis starts.
    """

    document = _find_owned_document(
        document_id=document_id,
        user_id=user_id,
    )

    if document is None:
        raise DocumentTypeDetectionNotFoundError(
            "The requested document was not found."
        )

    extracted_text = str(
        document.extracted_text or ""
    ).strip()

    if not extracted_text:
        raise DocumentTypeDetectionNotReadyError(
            "This document has no readable extracted text. "
            "It may require OCR before type detection."
        )

    try:
        detection = detect_document_type(
            filename=document.filename,
            extracted_text=extracted_text,
        )

    except DocumentTypeDetectionError as error:
        raise DocumentTypeDetectionWorkflowError(
            str(error)
        ) from error

    return OwnedDocumentTypeDetection(
        document=document,
        detection=detection,
    )


def _find_owned_document(
    *,
    document_id: int,
    user_id: int,
) -> Document | None:
    """Return a document only when its project belongs to the user."""

    return (
        Document.query
        .filter(
            Document.id == document_id,
            Document.user_id == user_id,
        )
        .first()
    )

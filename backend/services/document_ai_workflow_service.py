"""Persistence workflow for Document Brain AI analysis."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import (
    Document,
    DocumentAIAnalysis,
    Project,
)
from services.ai_service import (
    AIServiceError,
    analyze_document,
    get_ai_configuration,
)

from services.lifeos_activity_service import add_activity_event

from services.document_analysis_service import (
    DOCUMENT_ANALYSIS_SCHEMA_VERSION,
)
from services.document_type_detection_service import (
    ALLOWED_DETECTION_CONFIDENCE,
)
from services.document_type_profile_service import (
    get_document_type_label,
    resolve_document_type_key,
)
from services.document_task_suggestion_service import (
    DocumentSuggestionBuildError,
    build_document_task_suggestions,
)


class DocumentAnalysisWorkflowError(RuntimeError):
    """Raised when document analysis cannot be completed."""


class DocumentNotFoundError(DocumentAnalysisWorkflowError):
    """Raised when the document does not exist or is not owned."""


class DocumentNotReadyError(DocumentAnalysisWorkflowError):
    """Raised when a document has no readable extracted text."""


@dataclass(frozen=True)
class SavedDocumentAnalysis:
    """Result returned by the document-analysis workflow."""

    document: Document
    analysis: DocumentAIAnalysis
    reused_existing: bool


def analyse_owned_document(
    *,
    document_id: int,
    user_id: int,
    force: bool = False,
    confirmed_document_type: str | None = None,
    detected_document_type: str | None = None,
    detection_confidence: str | None = None,
) -> SavedDocumentAnalysis:
    """Analyse an owned document using its user-confirmed type."""

    document = _find_owned_document(
        document_id=document_id,
        user_id=user_id,
    )

    if document is None:
        raise DocumentNotFoundError(
            "The requested document was not found."
        )

    if document.is_historical_version:
        raise DocumentAnalysisWorkflowError(
            "This is a previous document version. Its saved analysis is "
            "kept as history; open the current version to run a new analysis."
        )

    extracted_text = str(
        document.extracted_text or ""
    ).strip()

    if not extracted_text:
        raise DocumentNotReadyError(
            "This document has no readable extracted text. "
            "It may require OCR before analysis."
        )

    confirmed_type_key: str | None = None

    if confirmed_document_type not in (
        None,
        "",
    ):
        confirmed_type_key = resolve_document_type_key(
            confirmed_document_type
        )

        if confirmed_type_key is None:
            raise DocumentAnalysisWorkflowError(
                "The confirmed document type is unsupported."
            )

    detected_type_key: str | None = None

    if detected_document_type not in (
        None,
        "",
    ):
        detected_type_key = resolve_document_type_key(
            detected_document_type
        )

        if detected_type_key is None:
            raise DocumentAnalysisWorkflowError(
                "The detected document type is unsupported."
            )

    cleaned_confidence = str(
        detection_confidence or ""
    ).strip().casefold()

    if (
        cleaned_confidence
        and cleaned_confidence
        not in ALLOWED_DETECTION_CONFIDENCE
    ):
        raise DocumentAnalysisWorkflowError(
            "The document-type confidence value is invalid."
        )

    fingerprint = _create_source_fingerprint(
        extracted_text,
        confirmed_document_type=confirmed_type_key,
    )

    if not force:
        existing_analysis = _find_reusable_analysis(
            document_id=document.id,
            user_id=user_id,
            fingerprint=fingerprint,
        )

        if existing_analysis is not None:
            return SavedDocumentAnalysis(
                document=document,
                analysis=existing_analysis,
                reused_existing=True,
            )

    try:
        result = analyze_document(
            filename=document.filename,
            extracted_text=extracted_text,
            confirmed_document_type=confirmed_type_key,
        )

    except AIServiceError as error:
        _save_failed_analysis(
            document=document,
            user_id=user_id,
            fingerprint=fingerprint,
            error=error,
            confirmed_document_type=confirmed_type_key,
        )

        raise DocumentAnalysisWorkflowError(
            str(error)
        ) from error

    analysis_data = dict(
        result["analysis"]
    )

    if confirmed_type_key is not None:
        if detected_type_key is None:
            type_source = "user_confirmed"
        elif detected_type_key == confirmed_type_key:
            type_source = "detected_confirmed"
        else:
            type_source = "user_override"

        analysis_data[
            "type_metadata"
        ] = {
            "detected_type_key": detected_type_key,
            "detected_type": (
                get_document_type_label(
                    detected_type_key
                )
                if detected_type_key
                else None
            ),
            "confirmed_type_key": confirmed_type_key,
            "confirmed_type": get_document_type_label(
                confirmed_type_key
            ),
            "source": type_source,
            "confidence": (
                cleaned_confidence
                or None
            ),
        }

    analysis = DocumentAIAnalysis(
        document_id=document.id,
        user_id=user_id,
        provider=str(
            result.get("provider") or "unknown"
        )[:30],
        model=str(
            result.get("model") or "unknown"
        )[:100],
        status="Completed",
        document_type=analysis_data.get(
            "document_type"
        ),
        summary=analysis_data.get("summary"),
        insights_json=json.dumps(
            analysis_data,
            ensure_ascii=False,
        ),
        source_fingerprint=fingerprint,
        error_message=None,
    )

    # Keep the latest executive summary available directly
    # on the Document record for document cards and previews.
    document.summary = analysis_data.get(
        "summary"
    )

    try:
        db.session.add(analysis)
        db.session.flush()

        suggestions = build_document_task_suggestions(
            analysis=analysis,
            document=document,
            user_id=user_id,
        )

        db.session.add_all(suggestions)
        add_activity_event(
            user_id=user_id,
            event_type="document.analysis_completed",
            object_type="document_analysis",
            object_id=analysis.id,
            project_id=document.project_id,
            title=f"Document analysis completed: {document.filename}",
            summary="LifeOS refreshed the document's structured intelligence.",
            changes={"document_id": document.id, "document_type": analysis.document_type},
            source_type="document_brain",
            source_id=document.id,
        )
        db.session.commit()

    except (
        SQLAlchemyError,
        DocumentSuggestionBuildError,
    ) as error:
        db.session.rollback()

        _save_failed_analysis(
            document=document,
            user_id=user_id,
            fingerprint=fingerprint,
            error=error,
            confirmed_document_type=confirmed_type_key,
        )

        raise DocumentAnalysisWorkflowError(
            "LifeOS generated the document analysis, "
            "but could not save it."
        ) from error

    return SavedDocumentAnalysis(
        document=document,
        analysis=analysis,
        reused_existing=False,
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


def _find_reusable_analysis(
    *,
    document_id: int,
    user_id: int,
    fingerprint: str,
) -> DocumentAIAnalysis | None:
    """Find a completed analysis for unchanged document text."""

    return (
        DocumentAIAnalysis.query
        .filter_by(
            document_id=document_id,
            user_id=user_id,
            status="Completed",
            source_fingerprint=fingerprint,
        )
        .order_by(
            DocumentAIAnalysis.created_at.desc(),
            DocumentAIAnalysis.id.desc(),
        )
        .first()
    )


def _create_source_fingerprint(
    extracted_text: str,
    *,
    confirmed_document_type: str | None = None,
) -> str:
    """Fingerprint document text, analysis schema, and confirmed type."""

    type_identity = (
        confirmed_document_type
        or "legacy_unconfirmed"
    )

    fingerprint_input = (
        f"{DOCUMENT_ANALYSIS_SCHEMA_VERSION}\n"
        f"{type_identity}\n"
        f"{extracted_text}"
    )

    return hashlib.sha256(
        fingerprint_input.encode(
            "utf-8"
        )
    ).hexdigest()


def _save_failed_analysis(
    *,
    document: Document,
    user_id: int,
    fingerprint: str,
    error: Exception,
    confirmed_document_type: str | None = None,
) -> None:
    """Record an unsuccessful AI analysis attempt."""

    provider, model = _safe_ai_identity()

    failed_analysis = DocumentAIAnalysis(
        document_id=document.id,
        user_id=user_id,
        provider=provider,
        model=model,
        status="Failed",
        document_type=(
            get_document_type_label(
                confirmed_document_type
            )
            if confirmed_document_type
            else None
        ),
        summary=None,
        insights_json=None,
        source_fingerprint=fingerprint,
        error_message=str(error)[:2000],
    )

    try:
        db.session.add(failed_analysis)
        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()


def _safe_ai_identity() -> tuple[str, str]:
    """Return provider information without hiding the original failure."""

    try:
        config = get_ai_configuration()

    except AIServiceError:
        return "unavailable", "unavailable"

    return (
        str(
            config.get("provider") or "unknown"
        )[:30],
        str(
            config.get("model") or "unknown"
        )[:100],
    )
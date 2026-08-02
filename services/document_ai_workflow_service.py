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
) -> SavedDocumentAnalysis:
    """Analyse an owned document and save its structured insights."""

    document = _find_owned_document(
        document_id=document_id,
        user_id=user_id,
    )

    if document is None:
        raise DocumentNotFoundError(
            "The requested document was not found."
        )

    extracted_text = str(
        document.extracted_text or ""
    ).strip()

    if not extracted_text:
        raise DocumentNotReadyError(
            "This document has no readable extracted text. "
            "It may require OCR before analysis."
        )

    fingerprint = _create_source_fingerprint(
        extracted_text
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
        )

    except AIServiceError as error:
        _save_failed_analysis(
            document=document,
            user_id=user_id,
            fingerprint=fingerprint,
            error=error,
        )

        raise DocumentAnalysisWorkflowError(
            str(error)
        ) from error

    analysis_data = result["analysis"]

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
        db.session.commit()
        

    except (SQLAlchemyError, DocumentSuggestionBuildError) as error:

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
        .join(
            Project,
            Document.project_id == Project.id,
        )
        .filter(
            Document.id == document_id,
            Project.user_id == user_id,
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
) -> str:
    """Create a stable SHA-256 fingerprint for document text."""

    return hashlib.sha256(
        extracted_text.encode("utf-8")
    ).hexdigest()


def _save_failed_analysis(
    *,
    document: Document,
    user_id: int,
    fingerprint: str,
    error: Exception,
) -> None:
    """Record an unsuccessful AI analysis attempt."""

    provider, model = _safe_ai_identity()

    failed_analysis = DocumentAIAnalysis(
        document_id=document.id,
        user_id=user_id,
        provider=provider,
        model=model,
        status="Failed",
        document_type=None,
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
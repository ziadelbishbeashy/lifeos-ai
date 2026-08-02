"""Persistent workflow for grounded Document Brain questions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import (
    Document,
    DocumentQuestion,
    Project,
)
from services.ai_service import (
    AIServiceError,
    MAX_QUESTION_CHARACTERS,
    ask_document_question,
    get_ai_configuration,
)


class DocumentQuestionWorkflowError(RuntimeError):
    """Raised when a document question cannot be completed."""


class DocumentQuestionNotFoundError(
    DocumentQuestionWorkflowError
):
    """Raised when the document is missing or not owned."""


class DocumentQuestionNotReadyError(
    DocumentQuestionWorkflowError
):
    """Raised when the document has no readable text."""


@dataclass(frozen=True)
class SavedDocumentQuestion:
    """Result of asking a grounded document question."""

    document: Document
    question: DocumentQuestion
    reused_existing: bool


def ask_owned_document(
    *,
    document_id: int,
    user_id: int,
    question_text: str,
    force: bool = False,
) -> SavedDocumentQuestion:
    """Answer and save a question about one owned document."""

    document = _find_owned_document(
        document_id=document_id,
        user_id=user_id,
    )

    if document is None:
        raise DocumentQuestionNotFoundError(
            "The requested document was not found."
        )

    extracted_text = str(
        document.extracted_text or ""
    ).strip()

    if not extracted_text:
        raise DocumentQuestionNotReadyError(
            "This document has no readable extracted text. "
            "It may require OCR before questions can be answered."
        )

    cleaned_question = " ".join(
        str(question_text or "").split()
    )

    if not cleaned_question:
        raise DocumentQuestionWorkflowError(
            "Enter a question about the document."
        )

    if len(cleaned_question) > MAX_QUESTION_CHARACTERS:
        raise DocumentQuestionWorkflowError(
            "The question is too long. "
            f"Use at most {MAX_QUESTION_CHARACTERS:,} characters."
        )

    source_fingerprint = _create_source_fingerprint(
        extracted_text
    )

    if not force:
        existing_question = _find_reusable_question(
            document_id=document.id,
            user_id=user_id,
            question_text=cleaned_question,
            fingerprint=source_fingerprint,
        )

        if existing_question is not None:
            return SavedDocumentQuestion(
                document=document,
                question=existing_question,
                reused_existing=True,
            )

    try:
        result = ask_document_question(
            filename=document.filename,
            extracted_text=extracted_text,
            question=cleaned_question,
        )

    except AIServiceError as error:
        _save_failed_question(
            document=document,
            user_id=user_id,
            question_text=cleaned_question,
            fingerprint=source_fingerprint,
            error=error,
        )

        raise DocumentQuestionWorkflowError(
            str(error)
        ) from error

    saved_question = DocumentQuestion(
        document_id=document.id,
        user_id=user_id,
        question=cleaned_question,
        answer=result["answer"],
        sources_json=json.dumps(
            result.get("sources", []),
            ensure_ascii=False,
        ),
        provider=str(
            result.get("provider") or "unknown"
        )[:30],
        model=str(
            result.get("model") or "unknown"
        )[:100],
        status="Completed",
        source_fingerprint=source_fingerprint,
        error_message=None,
    )

    try:
        db.session.add(saved_question)
        db.session.commit()

    except SQLAlchemyError as error:
        db.session.rollback()

        raise DocumentQuestionWorkflowError(
            "LifeOS generated the answer but could not save it."
        ) from error

    return SavedDocumentQuestion(
        document=document,
        question=saved_question,
        reused_existing=False,
    )


def list_owned_document_questions(
    *,
    document_id: int,
    user_id: int,
    limit: int = 20,
) -> list[DocumentQuestion]:
    """Return recent question history for one owned document."""

    document = _find_owned_document(
        document_id=document_id,
        user_id=user_id,
    )

    if document is None:
        raise DocumentQuestionNotFoundError(
            "The requested document was not found."
        )

    safe_limit = max(
        1,
        min(int(limit), 100),
    )

    return (
        DocumentQuestion.query
        .filter_by(
            document_id=document.id,
            user_id=user_id,
        )
        .order_by(
            DocumentQuestion.created_at.desc(),
            DocumentQuestion.id.desc(),
        )
        .limit(safe_limit)
        .all()
    )


def _find_owned_document(
    *,
    document_id: int,
    user_id: int,
) -> Document | None:
    """Return a document only when its project is owned."""

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


def _find_reusable_question(
    *,
    document_id: int,
    user_id: int,
    question_text: str,
    fingerprint: str,
) -> DocumentQuestion | None:
    """Reuse an identical completed question for unchanged text."""

    return (
        DocumentQuestion.query
        .filter_by(
            document_id=document_id,
            user_id=user_id,
            question=question_text,
            status="Completed",
            source_fingerprint=fingerprint,
        )
        .order_by(
            DocumentQuestion.created_at.desc(),
            DocumentQuestion.id.desc(),
        )
        .first()
    )


def _create_source_fingerprint(
    extracted_text: str,
) -> str:
    """Return a SHA-256 fingerprint of the document text."""

    return hashlib.sha256(
        extracted_text.encode("utf-8")
    ).hexdigest()


def _save_failed_question(
    *,
    document: Document,
    user_id: int,
    question_text: str,
    fingerprint: str,
    error: Exception,
) -> None:
    """Record a provider failure without hiding the original error."""

    provider, model = _safe_ai_identity()

    failed_question = DocumentQuestion(
        document_id=document.id,
        user_id=user_id,
        question=question_text,
        answer=None,
        sources_json=None,
        provider=provider,
        model=model,
        status="Failed",
        source_fingerprint=fingerprint,
        error_message=str(error)[:2000],
    )

    try:
        db.session.add(failed_question)
        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()


def _safe_ai_identity() -> tuple[str, str]:
    """Return configured provider details safely."""

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
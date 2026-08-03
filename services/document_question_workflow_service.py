"""Persistent RAG workflow for grounded Document Brain questions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

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

from services.document_hybrid_retrieval_service import (
    DocumentHybridRetrievalError,
    DocumentHybridRetrievalNotFoundError,
    DocumentHybridRetrievalNotReadyError,
    DocumentHybridRetrievalValidationError,
    build_hybrid_retrieval_context,
    retrieve_owned_document_chunks_hybrid,
)

QUESTION_WORKFLOW_VERSION = "document-question-hybrid-rag-v2"

RETRIEVAL_RESULT_LIMIT = 5
RETRIEVAL_CONTEXT_CHARACTERS = 14_000

NO_MATCH_ANSWER = (
    "LifeOS could not find information in this document "
    "that directly answers the question."
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
    """
    Retrieve relevant chunks, answer the question and save it.

    The AI receives only the chunks selected by retrieval rather
    than the document's complete extracted text.
    """

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
        retrieval_result = (
            retrieve_owned_document_chunks_hybrid(
                document_id=document.id,
                user_id=user_id,
                query=cleaned_question,
                limit=RETRIEVAL_RESULT_LIMIT,
            )
        )

    except DocumentHybridRetrievalNotFoundError as error:
        raise DocumentQuestionNotFoundError(
            str(error)
        ) from error

    except DocumentHybridRetrievalNotReadyError as error:
        raise DocumentQuestionNotReadyError(
            str(error)
        ) from error

    except DocumentHybridRetrievalValidationError as error:
        raise DocumentQuestionWorkflowError(
            str(error)
        ) from error

    except DocumentHybridRetrievalError as error:
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

    retrieval_context = build_hybrid_retrieval_context(
        retrieval_result,
        max_characters=RETRIEVAL_CONTEXT_CHARACTERS,
    )

    # BM25 can return no results when none of the meaningful
    # question terms occur inside the document.
    if not retrieval_context:
        result: dict[str, Any] = {
            "success": True,
            "provider": "lifeos",
            "model": "bm25-retrieval",
            "question": cleaned_question,
            "answer": NO_MATCH_ANSWER,
            "found_in_document": False,
            "sources": [],
            "input_characters": 0,
        }

    else:
        try:
            result = ask_document_question(
                filename=document.filename,
                extracted_text=retrieval_context,
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

    grounded_sources = []

    if result.get("found_in_document"):
        grounded_sources = _sources_from_retrieval(
            retrieval_result
        )

    saved_question = DocumentQuestion(
        document_id=document.id,
        user_id=user_id,
        question=cleaned_question,
        answer=str(
            result.get("answer") or ""
        ).strip(),
        sources_json=json.dumps(
            grounded_sources,
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
        db.session.add(
            saved_question
        )

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

    try:
        requested_limit = int(
            limit
        )

    except (
        TypeError,
        ValueError,
    ):
        requested_limit = 20

    safe_limit = max(
        1,
        min(
            requested_limit,
            100,
        ),
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
        .limit(
            safe_limit
        )
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
    """
    Fingerprint the document and current question workflow.

    Including the workflow version prevents old full-document
    answers from being reused after switching to RAG.
    """

    fingerprint_input = (
        f"{QUESTION_WORKFLOW_VERSION}\n"
        f"{str(extracted_text or '')}"
    )

    return hashlib.sha256(
        fingerprint_input.encode(
            "utf-8"
        )
    ).hexdigest()


def _sources_from_retrieval(
    retrieval_result: Any,
) -> list[dict[str, Any]]:
    """
    Build saved sources from actual retrieved chunks.

    We do not trust model-generated page references as the final
    database source. Sources are generated from the chunks that
    LifeOS actually supplied to the model.
    """

    sources: list[dict[str, Any]] = []
    seen_sources: set[tuple[str, str, str]] = set()

    for retrieved_chunk in retrieval_result.chunks:
        source = retrieved_chunk.source()

        page = source.get(
            "page"
        )

        section = str(
            source.get("section") or ""
        ).strip()

        evidence = str(
            source.get("evidence") or ""
        ).strip()

        source_key = (
            str(page or ""),
            section,
            evidence,
        )

        if source_key in seen_sources:
            continue

        seen_sources.add(
            source_key
        )

        sources.append(
            {
                "page": page,
                "section": section,
                "evidence": evidence,
            }
        )

    return sources


def _save_failed_question(
    *,
    document: Document,
    user_id: int,
    question_text: str,
    fingerprint: str,
    error: Exception,
) -> None:
    """Record a retrieval or provider failure."""

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
        db.session.add(
            failed_question
        )

        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()


def _safe_ai_identity() -> tuple[str, str]:
    """Return configured provider details safely."""

    try:
        config = get_ai_configuration()

    except AIServiceError:
        return (
            "unavailable",
            "unavailable",
        )

    return (
        str(
            config.get("provider") or "unknown"
        )[:30],
        str(
            config.get("model") or "unknown"
        )[:100],
    )
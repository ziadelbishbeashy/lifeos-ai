"""Persistent RAG workflow for grounded Document Brain questions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, is_dataclass, replace
from types import SimpleNamespace
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

from services.document_answerability_service import (
    DocumentAnswerabilityError,
    verify_document_answerability,
)

from services.document_evidence_preview_service import (
    build_focused_evidence_preview,
)

from services.document_rag_logging_service import (
    build_retrieval_log_summary,
    create_document_rag_trace_id,
    log_document_rag_event,
)


QUESTION_WORKFLOW_VERSION = (
    "document-question-focused-evidence-v8"
)

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
    """Retrieve evidence, validate claim citations and save the answer."""

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

    trace_id = create_document_rag_trace_id()

    log_document_rag_event(
        event="question_started",
        trace_id=trace_id,
        document_id=document.id,
        question=cleaned_question,
        force=bool(force),
        workflow_version=QUESTION_WORKFLOW_VERSION,
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
            log_document_rag_event(
                event="question_reused",
                trace_id=trace_id,
                document_id=document.id,
                question=cleaned_question,
                question_id=existing_question.id,
                status=existing_question.status,
            )

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
        _log_workflow_failure(
            trace_id=trace_id,
            document_id=document.id,
            question=cleaned_question,
            stage="retrieval",
            error=error,
        )

        raise DocumentQuestionNotFoundError(
            str(error)
        ) from error

    except DocumentHybridRetrievalNotReadyError as error:
        _log_workflow_failure(
            trace_id=trace_id,
            document_id=document.id,
            question=cleaned_question,
            stage="retrieval",
            error=error,
        )

        raise DocumentQuestionNotReadyError(
            str(error)
        ) from error

    except DocumentHybridRetrievalValidationError as error:
        _log_workflow_failure(
            trace_id=trace_id,
            document_id=document.id,
            question=cleaned_question,
            stage="retrieval",
            error=error,
        )

        raise DocumentQuestionWorkflowError(
            str(error)
        ) from error

    except DocumentHybridRetrievalError as error:
        _log_workflow_failure(
            trace_id=trace_id,
            document_id=document.id,
            question=cleaned_question,
            stage="retrieval",
            error=error,
        )
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

    log_document_rag_event(
        event="retrieval_completed",
        trace_id=trace_id,
        document_id=document.id,
        question=cleaned_question,
        retrieval=build_retrieval_log_summary(
            retrieval_result
        ),
    )

    answer_retrieval_result = retrieval_result

    retrieval_context = build_hybrid_retrieval_context(
        retrieval_result,
        max_characters=RETRIEVAL_CONTEXT_CHARACTERS,
    )

    if not retrieval_context:
        log_document_rag_event(
            event="answerability_completed",
            trace_id=trace_id,
            document_id=document.id,
            question=cleaned_question,
            verification_performed=False,
            answerable=False,
            confidence="not_run",
            verified_source_ids=[],
            verified_source_count=0,
            reason_code="empty_retrieval_context",
        )

        result: dict[str, Any] = _no_match_result(
            question=cleaned_question,
            provider="lifeos",
            model="hybrid-retrieval",
        )

    else:
        try:
            verification = verify_document_answerability(
                filename=document.filename,
                retrieved_context=retrieval_context,
                question=cleaned_question,
            )

        except DocumentAnswerabilityError as error:
            _log_workflow_failure(
                trace_id=trace_id,
                document_id=document.id,
                question=cleaned_question,
                stage="answerability",
                error=error,
            )

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

        log_document_rag_event(
            event="answerability_completed",
            trace_id=trace_id,
            document_id=document.id,
            question=cleaned_question,
            verification_performed=True,
            answerable=bool(
                verification.answerable
            ),
            confidence=str(
                getattr(
                    verification,
                    "confidence",
                    "",
                )
                or ""
            ),
            verified_source_ids=list(
                verification.source_ids
            ),
            verified_source_count=len(
                verification.source_ids
            ),
            verifier_provider=str(
                getattr(
                    verification,
                    "provider",
                    "",
                )
                or ""
            ),
            verifier_model=str(
                getattr(
                    verification,
                    "model",
                    "",
                )
                or ""
            ),
            verifier_input_characters=getattr(
                verification,
                "input_characters",
                None,
            ),
        )

        if not verification.answerable:
            result = _no_match_result(
                question=cleaned_question,
                provider=verification.provider,
                model=(
                    f"{verification.model}:answerability"
                ),
            )

        else:
            try:
                answer_retrieval_result = (
                    _select_verified_retrieval_sources(
                        retrieval_result=retrieval_result,
                        source_ids=verification.source_ids,
                    )
                )

            except DocumentQuestionWorkflowError as error:
                _log_workflow_failure(
                    trace_id=trace_id,
                    document_id=document.id,
                    question=cleaned_question,
                    stage="verified_source_selection",
                    error=error,
                )

                _save_failed_question(
                    document=document,
                    user_id=user_id,
                    question_text=cleaned_question,
                    fingerprint=source_fingerprint,
                    error=error,
                )

                raise

            verified_context = (
                build_hybrid_retrieval_context(
                    answer_retrieval_result,
                    max_characters=(
                        RETRIEVAL_CONTEXT_CHARACTERS
                    ),
                )
            )

            if not verified_context:
                error = DocumentQuestionWorkflowError(
                    "The verified document sources could not "
                    "be prepared for answering."
                )

                _log_workflow_failure(
                    trace_id=trace_id,
                    document_id=document.id,
                    question=cleaned_question,
                    stage="verified_context",
                    error=error,
                )

                _save_failed_question(
                    document=document,
                    user_id=user_id,
                    question_text=cleaned_question,
                    fingerprint=source_fingerprint,
                    error=error,
                )

                raise error

            try:
                result = ask_document_question(
                    filename=document.filename,
                    extracted_text=verified_context,
                    question=cleaned_question,
                )

            except AIServiceError as error:
                _log_workflow_failure(
                    trace_id=trace_id,
                    document_id=document.id,
                    question=cleaned_question,
                    stage="answer_generation",
                    error=error,
                )

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

            log_document_rag_event(
                event="answer_generation_completed",
                trace_id=trace_id,
                document_id=document.id,
                question=cleaned_question,
                provider=str(
                    result.get("provider") or ""
                ),
                model=str(
                    result.get("model") or ""
                ),
                found_in_document=bool(
                    result.get("found_in_document")
                ),
                claim_count=len(
                    result.get("claims") or []
                ),
                input_characters=result.get(
                    "input_characters"
                ),
            )

    grounded_sources: list[dict[str, Any]] = []
    saved_answer = str(
        result.get("answer") or ""
    ).strip()

    if result.get("found_in_document"):
        try:
            claims = result.get("claims") or []

            grounded_sources = _sources_from_claims(
                retrieval_result=answer_retrieval_result,
                claims=claims,
            )

            saved_answer = _answer_from_claims(
                claims
            )

        except DocumentQuestionWorkflowError as error:
            _log_workflow_failure(
                trace_id=trace_id,
                document_id=document.id,
                question=cleaned_question,
                stage="citation_validation",
                error=error,
            )

            _save_failed_question(
                document=document,
                user_id=user_id,
                question_text=cleaned_question,
                fingerprint=source_fingerprint,
                error=error,
            )

            raise

    if not saved_answer:
        error = DocumentQuestionWorkflowError(
            "LifeOS generated an empty document answer."
        )

        _log_workflow_failure(
            trace_id=trace_id,
            document_id=document.id,
            question=cleaned_question,
            stage="answer_validation",
            error=error,
        )

        raise error

    saved_question = DocumentQuestion(
        document_id=document.id,
        user_id=user_id,
        question=cleaned_question,
        answer=saved_answer,
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

        log_document_rag_event(
            event="question_saved",
            trace_id=trace_id,
            document_id=document.id,
            question=cleaned_question,
            question_id=saved_question.id,
            status=saved_question.status,
            provider=saved_question.provider,
            model=saved_question.model,
            found_in_document=bool(
                result.get("found_in_document")
            ),
            saved_source_count=len(
                grounded_sources
            ),
        )

    except SQLAlchemyError as error:
        db.session.rollback()

        _log_workflow_failure(
            trace_id=trace_id,
            document_id=document.id,
            question=cleaned_question,
            stage="database_save",
            error=error,
        )

        raise DocumentQuestionWorkflowError(
            "LifeOS generated the answer but could not save it."
        ) from error

    return SavedDocumentQuestion(
        document=document,
        question=saved_question,
        reused_existing=False,
    )



def _no_match_result(
    *,
    question: str,
    provider: str,
    model: str,
) -> dict[str, Any]:
    """Return a completed fail-closed no-answer result."""

    return {
        "success": True,
        "provider": str(provider or "lifeos")[:30],
        "model": str(model or "answerability-verifier")[:100],
        "question": question,
        "answer": NO_MATCH_ANSWER,
        "found_in_document": False,
        "claims": [],
        "input_characters": 0,
    }


def _select_verified_retrieval_sources(
    *,
    retrieval_result: Any,
    source_ids: tuple[int, ...] | list[int],
) -> Any:
    """Return a retrieval result containing only verified sources."""

    retrieved_chunks = list(
        retrieval_result.chunks or []
    )

    selected_chunks = []
    seen_source_ids: set[int] = set()

    for raw_source_id in source_ids:
        try:
            source_id = int(raw_source_id)

        except (TypeError, ValueError) as error:
            raise DocumentQuestionWorkflowError(
                "The answerability verifier returned an "
                "invalid source number."
            ) from error

        if source_id in seen_source_ids:
            continue

        if (
            source_id < 1
            or source_id > len(retrieved_chunks)
        ):
            raise DocumentQuestionWorkflowError(
                "The answerability verifier selected a source "
                "that was not supplied by retrieval."
            )

        seen_source_ids.add(source_id)
        selected_chunks.append(
            retrieved_chunks[source_id - 1]
        )

    if not selected_chunks:
        raise DocumentQuestionWorkflowError(
            "The answerability verifier did not select any "
            "usable document sources."
        )

    if is_dataclass(retrieval_result):
        return replace(
            retrieval_result,
            chunks=selected_chunks,
        )

    values = dict(
        vars(retrieval_result)
    )
    values["chunks"] = selected_chunks

    return SimpleNamespace(
        **values
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


def _sources_from_claims(
    *,
    retrieval_result: Any,
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Validate citations and build focused trusted source previews.

    The preview is selected from the full retrieved chunk using the
    question, claim wording and retrieval terms. It is never generated
    or paraphrased by the AI model.
    """

    retrieved_chunks = list(
        retrieval_result.chunks
    )

    if not claims:
        raise DocumentQuestionWorkflowError(
            "The answer did not include supported claims."
        )

    cited_source_ids: list[int] = []
    seen_source_ids: set[int] = set()
    claim_texts_by_source: dict[
        int,
        list[str],
    ] = {}

    for claim_number, claim in enumerate(
        claims,
        start=1,
    ):
        if not isinstance(claim, dict):
            raise DocumentQuestionWorkflowError(
                f"Claim {claim_number} is invalid."
            )

        claim_text = str(
            claim.get("text") or ""
        ).strip()

        if not claim_text:
            raise DocumentQuestionWorkflowError(
                f"Claim {claim_number} has no text."
            )

        raw_source_ids = claim.get("source_ids")

        if (
            not isinstance(
                raw_source_ids,
                list,
            )
            or not raw_source_ids
        ):
            raise DocumentQuestionWorkflowError(
                f"Claim {claim_number} did not cite a source."
            )

        for raw_source_id in raw_source_ids:
            try:
                source_id = int(
                    raw_source_id
                )

            except (
                TypeError,
                ValueError,
            ) as error:
                raise DocumentQuestionWorkflowError(
                    f"Claim {claim_number} returned an invalid "
                    "source citation."
                ) from error

            if (
                source_id < 1
                or source_id > len(
                    retrieved_chunks
                )
            ):
                raise DocumentQuestionWorkflowError(
                    f"Claim {claim_number} cited a source that "
                    "was not supplied by document retrieval."
                )

            claim_texts_by_source.setdefault(
                source_id,
                [],
            ).append(
                claim_text
            )

            if source_id in seen_source_ids:
                continue

            seen_source_ids.add(
                source_id
            )

            cited_source_ids.append(
                source_id
            )

    sources: list[dict[str, Any]] = []

    retrieval_query = str(
        getattr(
            retrieval_result,
            "query",
            "",
        )
        or ""
    ).strip()

    for source_id in cited_source_ids:
        retrieved_source = retrieved_chunks[
            source_id - 1
        ]

        trusted_source = (
            retrieved_source.source()
        )

        full_source_text = str(
            getattr(
                retrieved_source,
                "text",
                "",
            )
            or ""
        ).strip()

        if not full_source_text:
            database_chunk = getattr(
                retrieved_source,
                "chunk",
                None,
            )

            full_source_text = str(
                getattr(
                    database_chunk,
                    "text",
                    "",
                )
                or ""
            ).strip()

        if not full_source_text:
            full_source_text = str(
                trusted_source.get(
                    "evidence"
                )
                or ""
            ).strip()

        claim_focus = " ".join(
            claim_texts_by_source.get(
                source_id,
                [],
            )
        ).strip()

        matched_terms = tuple(
            getattr(
                retrieved_source,
                "matched_terms",
                (),
            )
            or ()
        )

        preview = (
            build_focused_evidence_preview(
                full_source_text,
                question=retrieval_query,
                claim_text=claim_focus,
                matched_terms=matched_terms,
            )
        )

        sources.append(
            {
                "source_id": source_id,
                "page": trusted_source.get(
                    "page"
                ),
                "section": str(
                    trusted_source.get(
                        "section"
                    )
                    or ""
                ).strip(),
                "evidence": preview.text,
                "preview_type": (
                    "focused"
                    if preview.focused
                    else "leading"
                ),
            }
        )

    if not sources:
        raise DocumentQuestionWorkflowError(
            "The answer did not contain a valid source citation."
        )

    return sources


def _answer_from_claims(
    claims: list[dict[str, Any]],
) -> str:
    """Build the stored answer from validated claim citations."""

    answer_parts: list[str] = []

    for claim in claims:
        text = str(
            claim.get("text") or ""
        ).strip()

        source_ids = claim.get("source_ids") or []
        source_labels = ", ".join(
            f"Source {int(source_id)}"
            for source_id in source_ids
        )

        if text and source_labels:
            answer_parts.append(
                f"{text} [{source_labels}]"
            )

    answer = " ".join(answer_parts).strip()

    if not answer:
        raise DocumentQuestionWorkflowError(
            "The answer did not contain supported claims."
        )

    return answer




def _log_workflow_failure(
    *,
    trace_id: str,
    document_id: int,
    question: str,
    stage: str,
    error: Exception,
) -> None:
    """
    Log a workflow failure without exposing its message.

    Exception messages are excluded because provider and validation
    messages can contain document-derived information.
    """

    log_document_rag_event(
        event="workflow_failed",
        trace_id=trace_id,
        document_id=document_id,
        question=question,
        level="error",
        stage=str(
            stage or "unknown"
        ),
        error_type=type(
            error
        ).__name__,
    )


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

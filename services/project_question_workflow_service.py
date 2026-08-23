"""Persistent project-wide multi-document RAG workflow for LifeOS."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import Document, Project, ProjectQuestion
from services.ai_service import (
    AIServiceError,
    MAX_QUESTION_CHARACTERS,
    ask_project_documents_question,
    get_ai_configuration,
)
from services.document_answerability_service import (
    DocumentAnswerabilityError,
    verify_document_answerability,
)
from services.document_evidence_preview_service import (
    build_focused_evidence_preview,
)
from services.project_document_retrieval_service import (
    ProjectDocumentRetrievalError,
    ProjectDocumentRetrievalNotFoundError,
    ProjectDocumentRetrievalNotReadyError,
    ProjectDocumentRetrievalResult,
    ProjectDocumentRetrievalValidationError,
    build_project_retrieval_context,
    retrieve_owned_project_document_chunks,
    select_project_retrieval_sources,
)
from services.document_version_service import (
    current_document_filter,
)


PROJECT_QUESTION_WORKFLOW_VERSION = "project-document-rag-v1"
PROJECT_RETRIEVAL_RESULT_LIMIT = 10
PROJECT_RETRIEVAL_CONTEXT_CHARACTERS = 16_000

NO_MATCH_ANSWER = (
    "LifeOS could not find enough evidence across the linked project "
    "documents to answer that question."
)


class ProjectQuestionWorkflowError(RuntimeError):
    """Raised when a project-wide document question cannot be completed."""


class ProjectQuestionNotFoundError(ProjectQuestionWorkflowError):
    """Raised when the project is missing or not owned."""


class ProjectQuestionNotReadyError(ProjectQuestionWorkflowError):
    """Raised when the project has no searchable linked PDFs."""


@dataclass(frozen=True)
class SavedProjectQuestion:
    project: Project
    question: ProjectQuestion
    reused_existing: bool


def ask_owned_project_documents(
    *,
    project_id: int,
    user_id: int,
    question_text: str,
    force: bool = False,
) -> SavedProjectQuestion:
    """Retrieve across all linked PDFs, verify evidence, answer and persist."""

    project = _find_owned_project(
        project_id=project_id,
        user_id=user_id,
    )

    cleaned_question = " ".join(
        str(question_text or "").split()
    ).strip()

    if not cleaned_question:
        raise ProjectQuestionWorkflowError(
            "Enter a question about the project's documents."
        )

    if len(cleaned_question) > MAX_QUESTION_CHARACTERS:
        raise ProjectQuestionWorkflowError(
            "The question is too long. "
            f"Use at most {MAX_QUESTION_CHARACTERS:,} characters."
        )

    source_fingerprint = create_project_document_source_fingerprint(
        project_id=project.id,
        user_id=user_id,
    )

    if not force:
        existing = _find_reusable_question(
            project_id=project.id,
            user_id=user_id,
            question_text=cleaned_question,
            fingerprint=source_fingerprint,
        )

        if existing is not None:
            return SavedProjectQuestion(
                project=project,
                question=existing,
                reused_existing=True,
            )

    try:
        retrieval_result = retrieve_owned_project_document_chunks(
            project_id=project.id,
            user_id=user_id,
            query=cleaned_question,
            limit=PROJECT_RETRIEVAL_RESULT_LIMIT,
        )

    except ProjectDocumentRetrievalNotFoundError as error:
        raise ProjectQuestionNotFoundError(str(error)) from error

    except ProjectDocumentRetrievalNotReadyError as error:
        raise ProjectQuestionNotReadyError(str(error)) from error

    except ProjectDocumentRetrievalValidationError as error:
        raise ProjectQuestionWorkflowError(str(error)) from error

    except ProjectDocumentRetrievalError as error:
        _save_failed_question(
            project=project,
            user_id=user_id,
            question_text=cleaned_question,
            fingerprint=source_fingerprint,
            error=error,
        )
        raise ProjectQuestionWorkflowError(str(error)) from error

    retrieval_context = build_project_retrieval_context(
        retrieval_result,
        max_characters=PROJECT_RETRIEVAL_CONTEXT_CHARACTERS,
    )

    answer_retrieval_result = retrieval_result

    if not retrieval_context:
        result = _no_match_result(
            question=cleaned_question,
            provider="lifeos",
            model="project-hybrid-retrieval",
        )

    else:
        try:
            verification = verify_document_answerability(
                filename=f"{project.title} — linked project documents",
                retrieved_context=retrieval_context,
                question=cleaned_question,
            )

        except DocumentAnswerabilityError as error:
            _save_failed_question(
                project=project,
                user_id=user_id,
                question_text=cleaned_question,
                fingerprint=source_fingerprint,
                error=error,
            )
            raise ProjectQuestionWorkflowError(str(error)) from error

        if not verification.answerable:
            result = _no_match_result(
                question=cleaned_question,
                provider=verification.provider,
                model=f"{verification.model}:answerability",
            )

        else:
            try:
                answer_retrieval_result = select_project_retrieval_sources(
                    retrieval_result=retrieval_result,
                    source_ids=verification.source_ids,
                )
            except ProjectDocumentRetrievalValidationError as error:
                _save_failed_question(
                    project=project,
                    user_id=user_id,
                    question_text=cleaned_question,
                    fingerprint=source_fingerprint,
                    error=error,
                )
                raise ProjectQuestionWorkflowError(str(error)) from error

            verified_context = build_project_retrieval_context(
                answer_retrieval_result,
                max_characters=PROJECT_RETRIEVAL_CONTEXT_CHARACTERS,
            )

            if not verified_context:
                error = ProjectQuestionWorkflowError(
                    "The verified project document sources could not be prepared."
                )
                _save_failed_question(
                    project=project,
                    user_id=user_id,
                    question_text=cleaned_question,
                    fingerprint=source_fingerprint,
                    error=error,
                )
                raise error

            try:
                result = ask_project_documents_question(
                    project_title=project.title,
                    retrieved_context=verified_context,
                    question=cleaned_question,
                )
            except AIServiceError as error:
                _save_failed_question(
                    project=project,
                    user_id=user_id,
                    question_text=cleaned_question,
                    fingerprint=source_fingerprint,
                    error=error,
                )
                raise ProjectQuestionWorkflowError(str(error)) from error

    grounded_sources: list[dict[str, Any]] = []
    saved_answer = str(result.get("answer") or "").strip()

    if result.get("found_in_document"):
        claims = result.get("claims") or []

        grounded_sources = _sources_from_claims(
            retrieval_result=answer_retrieval_result,
            claims=claims,
        )

        saved_answer = _answer_from_claims(claims)

    if not saved_answer:
        raise ProjectQuestionWorkflowError(
            "LifeOS generated an empty project document answer."
        )

    saved_question = ProjectQuestion(
        project_id=project.id,
        user_id=user_id,
        question=cleaned_question,
        answer=saved_answer,
        sources_json=json.dumps(
            grounded_sources,
            ensure_ascii=False,
        ),
        provider=str(result.get("provider") or "unknown")[:30],
        model=str(result.get("model") or "unknown")[:100],
        status="Completed",
        source_fingerprint=source_fingerprint,
        error_message=None,
    )

    try:
        db.session.add(saved_question)
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise ProjectQuestionWorkflowError(
            "LifeOS generated the answer but could not save it."
        ) from error

    return SavedProjectQuestion(
        project=project,
        question=saved_question,
        reused_existing=False,
    )


def list_owned_project_questions(
    *,
    project_id: int,
    user_id: int,
    limit: int = 40,
) -> list[ProjectQuestion]:
    """Return saved project-document questions after ownership validation."""

    project = _find_owned_project(
        project_id=project_id,
        user_id=user_id,
    )

    cleaned_limit = max(1, min(int(limit), 100))

    return (
        ProjectQuestion.query
        .filter_by(
            project_id=project.id,
            user_id=user_id,
        )
        .order_by(
            ProjectQuestion.created_at.desc(),
            ProjectQuestion.id.desc(),
        )
        .limit(cleaned_limit)
        .all()
    )


def create_project_document_source_fingerprint(
    *,
    project_id: int,
    user_id: int,
) -> str:
    """Fingerprint all readable linked PDFs so cached answers become stale safely."""

    project = _find_owned_project(
        project_id=project_id,
        user_id=user_id,
    )

    documents = (
        Document.query
        .filter(
            Document.project_id == project.id,
            current_document_filter(),
        )
        .order_by(Document.id.asc())
        .all()
    )

    readable_documents = [
        document
        for document in documents
        if str(document.extracted_text or "").strip()
    ]

    if not readable_documents:
        raise ProjectQuestionNotReadyError(
            "This project does not have any readable linked documents yet."
        )

    parts = [PROJECT_QUESTION_WORKFLOW_VERSION, f"project:{project.id}"]

    for document in readable_documents:
        content_hash = hashlib.sha256(
            str(document.extracted_text or "").encode("utf-8")
        ).hexdigest()
        parts.append(
            f"document:{document.id}:{document.filename}:{content_hash}"
        )

    return hashlib.sha256(
        "\n".join(parts).encode("utf-8")
    ).hexdigest()


def _sources_from_claims(
    *,
    retrieval_result: ProjectDocumentRetrievalResult,
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate citations and build trusted multi-document source previews."""

    retrieved_chunks = list(retrieval_result.chunks)

    if not claims:
        raise ProjectQuestionWorkflowError(
            "The answer did not include supported claims."
        )

    cited_source_ids: list[int] = []
    seen_source_ids: set[int] = set()
    claim_texts_by_source: dict[int, list[str]] = {}

    for claim_number, claim in enumerate(claims, start=1):
        if not isinstance(claim, dict):
            raise ProjectQuestionWorkflowError(
                f"Claim {claim_number} is invalid."
            )

        claim_text = str(claim.get("text") or "").strip()
        raw_source_ids = claim.get("source_ids")

        if not claim_text or not isinstance(raw_source_ids, list) or not raw_source_ids:
            raise ProjectQuestionWorkflowError(
                f"Claim {claim_number} did not include a valid source citation."
            )

        for raw_source_id in raw_source_ids:
            try:
                source_id = int(raw_source_id)
            except (TypeError, ValueError) as error:
                raise ProjectQuestionWorkflowError(
                    f"Claim {claim_number} returned an invalid source citation."
                ) from error

            if source_id < 1 or source_id > len(retrieved_chunks):
                raise ProjectQuestionWorkflowError(
                    f"Claim {claim_number} cited a source that was not supplied."
                )

            claim_texts_by_source.setdefault(source_id, []).append(claim_text)

            if source_id not in seen_source_ids:
                seen_source_ids.add(source_id)
                cited_source_ids.append(source_id)

    sources: list[dict[str, Any]] = []

    for source_id in cited_source_ids:
        retrieved_source = retrieved_chunks[source_id - 1]
        trusted_source = retrieved_source.source()

        full_source_text = str(retrieved_source.text or "").strip()
        claim_focus = " ".join(claim_texts_by_source.get(source_id, [])).strip()

        preview = build_focused_evidence_preview(
            full_source_text,
            question=retrieval_result.query,
            claim_text=claim_focus,
            matched_terms=tuple(retrieved_source.matched_terms or ()),
        )

        sources.append(
            {
                "source_id": source_id,
                "project_id": retrieval_result.project.id,
                "document_id": trusted_source.get("document_id"),
                "filename": trusted_source.get("filename"),
                "chunk_id": trusted_source.get("chunk_id"),
                "chunk_index": trusted_source.get("chunk_index"),
                "page": trusted_source.get("page"),
                "section": str(trusted_source.get("section") or "").strip(),
                "evidence": preview.text,
                "preview_type": "focused" if preview.focused else "leading",
                "visibility": "project_owner",
            }
        )

    if not sources:
        raise ProjectQuestionWorkflowError(
            "The answer did not contain a valid project document citation."
        )

    return sources


def _answer_from_claims(claims: list[dict[str, Any]]) -> str:
    parts: list[str] = []

    for claim in claims:
        text = str(claim.get("text") or "").strip()
        source_ids = claim.get("source_ids") or []
        labels = ", ".join(f"Source {int(source_id)}" for source_id in source_ids)

        if text and labels:
            parts.append(f"{text} [{labels}]")

    answer = " ".join(parts).strip()

    if not answer:
        raise ProjectQuestionWorkflowError(
            "The answer did not contain supported claims."
        )

    return answer


def _no_match_result(*, question: str, provider: str, model: str) -> dict[str, Any]:
    return {
        "success": True,
        "provider": str(provider or "lifeos")[:30],
        "model": str(model or "project-answerability")[:100],
        "question": question,
        "answer": NO_MATCH_ANSWER,
        "found_in_document": False,
        "claims": [],
        "input_characters": 0,
    }


def _find_owned_project(*, project_id: int, user_id: int) -> Project:
    project = (
        Project.query
        .filter_by(id=project_id, user_id=user_id)
        .first()
    )

    if project is None:
        raise ProjectQuestionNotFoundError(
            "The project could not be found."
        )

    return project


def _find_reusable_question(
    *,
    project_id: int,
    user_id: int,
    question_text: str,
    fingerprint: str,
) -> ProjectQuestion | None:
    return (
        ProjectQuestion.query
        .filter_by(
            project_id=project_id,
            user_id=user_id,
            question=question_text,
            status="Completed",
            source_fingerprint=fingerprint,
        )
        .order_by(
            ProjectQuestion.created_at.desc(),
            ProjectQuestion.id.desc(),
        )
        .first()
    )


def _save_failed_question(
    *,
    project: Project,
    user_id: int,
    question_text: str,
    fingerprint: str,
    error: Exception,
) -> None:
    provider, model = _safe_ai_identity()

    failed = ProjectQuestion(
        project_id=project.id,
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
        db.session.add(failed)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()


def _safe_ai_identity() -> tuple[str, str]:
    try:
        config = get_ai_configuration()
    except AIServiceError:
        return "unavailable", "unavailable"

    return (
        str(config.get("provider") or "unknown")[:30],
        str(config.get("model") or "unknown")[:100],
    )

"""Grounded Ask Module / Ask Lecture workflow for Modules V1."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import (
    DocumentCollectionItem,
    LearningModule,
    Lecture,
    ModuleCollectionLink,
    ModuleDocumentLink,
    ModuleQuestion,
)
from services.ai_service import (
    AIServiceError,
    MAX_QUESTION_CHARACTERS,
    ask_document_scope_question,
    get_ai_configuration,
)
from services.document_answerability_service import (
    DocumentAnswerabilityError,
    verify_document_answerability,
)
from services.document_evidence_preview_service import build_focused_evidence_preview
from services.document_scope_retrieval_service import (
    DocumentScopeRetrievalError,
    DocumentScopeRetrievalNotReadyError,
    DocumentScopeRetrievalResult,
    DocumentScopeRetrievalValidationError,
    build_scope_context,
    retrieve_owned_document_set,
    select_scope_sources,
)
from services.module_service import ModuleNotFoundError, require_owned_lecture, require_owned_module

MODULE_QUESTION_WORKFLOW_VERSION = "module-rag-v1"
NO_MATCH_ANSWER = "LifeOS could not find enough evidence in this module to answer that question."
LECTURE_NO_MATCH_ANSWER = "LifeOS could not find enough evidence in this lecture to answer that question."


class ModuleQuestionWorkflowError(RuntimeError):
    pass


class ModuleQuestionNotFoundError(ModuleQuestionWorkflowError):
    pass


class ModuleQuestionNotReadyError(ModuleQuestionWorkflowError):
    pass


@dataclass(frozen=True)
class SavedModuleQuestion:
    module: LearningModule
    lecture: Lecture | None
    question: ModuleQuestion
    reused_existing: bool


def ask_owned_module_documents(
    *,
    module_id: int,
    user_id: int,
    question_text: str,
    lecture_id: int | None = None,
    force: bool = False,
) -> SavedModuleQuestion:
    try:
        module = require_owned_module(module_id, user_id)
        lecture = (
            require_owned_lecture(module_id=module.id, lecture_id=lecture_id, user_id=user_id)
            if lecture_id is not None
            else None
        )
    except ModuleNotFoundError as error:
        raise ModuleQuestionNotFoundError(str(error)) from error

    question = " ".join(str(question_text or "").split()).strip()
    if not question:
        raise ModuleQuestionWorkflowError("Enter a question about the module documents.")
    if len(question) > MAX_QUESTION_CHARACTERS:
        raise ModuleQuestionWorkflowError(
            f"The question is too long. Use at most {MAX_QUESTION_CHARACTERS:,} characters."
        )

    fingerprint = create_module_source_fingerprint(
        module_id=module.id,
        user_id=user_id,
        lecture_id=lecture.id if lecture is not None else None,
    )

    if not force:
        existing_query = ModuleQuestion.query.filter_by(
            module_id=module.id,
            lecture_id=lecture.id if lecture is not None else None,
            user_id=user_id,
            question=question,
            status="Completed",
            source_fingerprint=fingerprint,
        )
        existing = existing_query.order_by(
            ModuleQuestion.created_at.desc(), ModuleQuestion.id.desc()
        ).first()
        if existing is not None:
            return SavedModuleQuestion(module, lecture, existing, True)

    documents = _scope_documents(module.id, user_id, lecture.id if lecture else None)
    try:
        retrieval = retrieve_owned_document_set(
            documents=documents,
            user_id=user_id,
            query=question,
            visibility="module_owner" if lecture is None else "lecture_owner",
        )
    except DocumentScopeRetrievalNotReadyError as error:
        raise ModuleQuestionNotReadyError(str(error)) from error
    except (DocumentScopeRetrievalValidationError, DocumentScopeRetrievalError) as error:
        _save_failed(module, lecture, user_id, question, fingerprint, error)
        raise ModuleQuestionWorkflowError(str(error)) from error

    context = build_scope_context(retrieval)
    answer_retrieval = retrieval
    no_match = LECTURE_NO_MATCH_ANSWER if lecture is not None else NO_MATCH_ANSWER

    if not context:
        result = _no_match(question, "lifeos", "module-hybrid-retrieval", no_match)
    else:
        label = f"Lecture: {lecture.title}" if lecture is not None else f"Module: {module.title}"
        try:
            verification = verify_document_answerability(
                filename=label,
                retrieved_context=context,
                question=question,
            )
        except DocumentAnswerabilityError as error:
            _save_failed(module, lecture, user_id, question, fingerprint, error)
            raise ModuleQuestionWorkflowError(str(error)) from error

        if not verification.answerable:
            result = _no_match(
                question,
                verification.provider,
                f"{verification.model}:answerability",
                no_match,
            )
        else:
            try:
                answer_retrieval = select_scope_sources(
                    retrieval_result=retrieval,
                    source_ids=verification.source_ids,
                )
            except DocumentScopeRetrievalValidationError as error:
                _save_failed(module, lecture, user_id, question, fingerprint, error)
                raise ModuleQuestionWorkflowError(str(error)) from error

            try:
                result = ask_document_scope_question(
                    scope_label="Lecture" if lecture is not None else "Module",
                    scope_name=lecture.title if lecture is not None else module.title,
                    retrieved_context=build_scope_context(answer_retrieval),
                    question=question,
                )
            except AIServiceError as error:
                _save_failed(module, lecture, user_id, question, fingerprint, error)
                raise ModuleQuestionWorkflowError(str(error)) from error

    sources: list[dict[str, Any]] = []
    answer = str(result.get("answer") or "").strip()
    if result.get("found_in_document"):
        claims = result.get("claims") or []
        sources = _sources(answer_retrieval, claims)
        answer = _answer(claims)
    if not answer:
        raise ModuleQuestionWorkflowError("LifeOS generated an empty module answer.")

    row = ModuleQuestion(
        module_id=module.id,
        lecture_id=lecture.id if lecture is not None else None,
        user_id=user_id,
        question=question,
        answer=answer,
        sources_json=json.dumps(sources, ensure_ascii=False),
        provider=str(result.get("provider") or "unknown")[:30],
        model=str(result.get("model") or "unknown")[:100],
        status="Completed",
        source_fingerprint=fingerprint,
        error_message=None,
    )
    try:
        db.session.add(row)
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise ModuleQuestionWorkflowError(
            "LifeOS generated the answer but could not save it."
        ) from error
    return SavedModuleQuestion(module, lecture, row, False)


def list_owned_module_questions(
    *, module_id: int, user_id: int, lecture_id: int | None = None, limit: int = 50
) -> list[ModuleQuestion]:
    try:
        module = require_owned_module(module_id, user_id)
        if lecture_id is not None:
            require_owned_lecture(module_id=module.id, lecture_id=lecture_id, user_id=user_id)
    except ModuleNotFoundError as error:
        raise ModuleQuestionNotFoundError(str(error)) from error

    query = ModuleQuestion.query.filter_by(module_id=module.id, user_id=user_id)
    if lecture_id is None:
        query = query.filter(ModuleQuestion.lecture_id.is_(None))
    else:
        query = query.filter(ModuleQuestion.lecture_id == lecture_id)
    return query.order_by(
        ModuleQuestion.created_at.desc(), ModuleQuestion.id.desc()
    ).limit(max(1, min(int(limit), 100))).all()


def create_module_source_fingerprint(
    *, module_id: int, user_id: int, lecture_id: int | None = None
) -> str:
    try:
        module = require_owned_module(module_id, user_id)
        lecture = (
            require_owned_lecture(module_id=module.id, lecture_id=lecture_id, user_id=user_id)
            if lecture_id is not None
            else None
        )
    except ModuleNotFoundError as error:
        raise ModuleQuestionNotFoundError(str(error)) from error

    documents = _scope_documents(module.id, user_id, lecture.id if lecture else None)
    readable = [document for document in documents if _has_searchable_content(document)]
    if not readable:
        scope = "lecture" if lecture is not None else "module"
        raise ModuleQuestionNotReadyError(
            f"This {scope} does not have any readable current documents or structured tables yet."
        )

    parts = [
        MODULE_QUESTION_WORKFLOW_VERSION,
        f"module:{module.id}",
        f"lecture:{lecture.id if lecture is not None else 'all'}",
    ]
    for document in sorted(readable, key=lambda item: item.id):
        text_hash = hashlib.sha256(str(document.extracted_text or "").encode()).hexdigest()
        table_parts = []
        for table in getattr(document, "tables", []):
            table_hash = hashlib.sha256(str(table.markdown_text or "").encode()).hexdigest()
            table_parts.append(
                f"{table.page_number}:{table.table_index}:{table.source_fingerprint}:{table_hash}"
            )
        parts.append(
            f"document:{document.id}:{document.filename}:{text_hash}:{'|'.join(sorted(table_parts))}"
        )
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def list_owned_module_scope_documents(
    *, module_id: int, user_id: int, lecture_id: int | None = None
):
    """Return the exact current document scope used by Ask Module/Ask Lecture.

    Step 18 calls this public adapter so evaluation exercises the production
    module scoping rules instead of duplicating them in an evaluation-only path.
    """

    try:
        module = require_owned_module(module_id, user_id)
        lecture = (
            require_owned_lecture(
                module_id=module.id, lecture_id=lecture_id, user_id=user_id
            )
            if lecture_id is not None
            else None
        )
    except ModuleNotFoundError as error:
        raise ModuleQuestionNotFoundError(str(error)) from error

    return _scope_documents(
        module.id, user_id, lecture.id if lecture is not None else None
    )


def _scope_documents(module_id: int, user_id: int, lecture_id: int | None):
    """Return the current owned documents visible to an Ask Module/Lecture scope.

    Lecture questions stay deliberately narrow: only documents explicitly assigned
    to that lecture participate.  Module-wide questions additionally see documents
    inside Collections linked to the Module.  This makes Collections useful as
    focused document groups without creating a second retrieval implementation.
    """

    link_query = ModuleDocumentLink.query.filter(
        ModuleDocumentLink.module_id == module_id,
    )
    if lecture_id is not None:
        link_query = link_query.filter(ModuleDocumentLink.lecture_id == lecture_id)

    links = link_query.order_by(
        ModuleDocumentLink.added_at.asc(),
        ModuleDocumentLink.id.asc(),
    ).all()

    documents_by_id = {}

    def add_if_visible(document):
        if document is None:
            return
        if int(getattr(document, "user_id", 0) or 0) != int(user_id):
            return
        if not bool(getattr(document, "is_current_version", True)):
            return
        documents_by_id.setdefault(document.id, document)

    for link in links:
        add_if_visible(link.document)

    # Collections are module-level scopes, not lecture-level scopes.  A linked
    # collection therefore contributes to Ask Module only.
    if lecture_id is None:
        collection_links = (
            ModuleCollectionLink.query
            .filter(ModuleCollectionLink.module_id == module_id)
            .order_by(ModuleCollectionLink.added_at.asc(), ModuleCollectionLink.id.asc())
            .all()
        )
        collection_ids = [link.collection_id for link in collection_links]
        if collection_ids:
            collection_items = (
                DocumentCollectionItem.query
                .filter(DocumentCollectionItem.collection_id.in_(collection_ids))
                .order_by(DocumentCollectionItem.added_at.asc(), DocumentCollectionItem.id.asc())
                .all()
            )
            for item in collection_items:
                add_if_visible(item.document)

    return list(documents_by_id.values())


def _has_searchable_content(document) -> bool:
    if str(document.extracted_text or "").strip():
        return True
    return any(
        str(table.markdown_text or "").strip()
        for table in getattr(document, "tables", [])
    )


def _sources(retrieval: DocumentScopeRetrievalResult, claims: list[dict[str, Any]]):
    if not claims:
        raise ModuleQuestionWorkflowError("The answer did not include supported claims.")
    chunks = list(retrieval.chunks)
    ordered: list[int] = []
    seen: set[int] = set()
    claim_texts: dict[int, list[str]] = {}

    for index, claim in enumerate(claims, start=1):
        if not isinstance(claim, dict):
            raise ModuleQuestionWorkflowError(f"Claim {index} is invalid.")
        text = str(claim.get("text") or "").strip()
        source_ids = claim.get("source_ids")
        if not text or not isinstance(source_ids, list) or not source_ids:
            raise ModuleQuestionWorkflowError(
                f"Claim {index} did not include a valid source citation."
            )
        for raw_id in source_ids:
            try:
                source_id = int(raw_id)
            except (TypeError, ValueError) as error:
                raise ModuleQuestionWorkflowError(
                    f"Claim {index} returned an invalid source citation."
                ) from error
            if source_id < 1 or source_id > len(chunks):
                raise ModuleQuestionWorkflowError(
                    f"Claim {index} cited a source that was not supplied."
                )
            claim_texts.setdefault(source_id, []).append(text)
            if source_id not in seen:
                seen.add(source_id)
                ordered.append(source_id)

    output = []
    for source_id in ordered:
        source = chunks[source_id - 1]
        trusted = source.source()
        preview = build_focused_evidence_preview(
            str(source.text or "").strip(),
            question=retrieval.query,
            claim_text=" ".join(claim_texts.get(source_id, [])),
            matched_terms=tuple(source.matched_terms or ()),
        )
        output.append(
            {
                "source_id": source_id,
                "document_id": trusted.get("document_id"),
                "filename": trusted.get("filename"),
                "content_type": trusted.get("content_type"),
                "table_id": trusted.get("table_id"),
                "page": trusted.get("page"),
                "section": str(trusted.get("section") or "").strip(),
                "evidence": preview.text,
                "preview_type": "focused" if preview.focused else "leading",
                "visibility": trusted.get("visibility") or "module_owner",
            }
        )
    return output


def _answer(claims):
    parts = []
    for claim in claims:
        text = str(claim.get("text") or "").strip()
        source_ids = claim.get("source_ids") or []
        labels = ", ".join(f"Source {int(value)}" for value in source_ids)
        if text and labels:
            parts.append(f"{text} [{labels}]")
    answer = " ".join(parts).strip()
    if not answer:
        raise ModuleQuestionWorkflowError("The answer did not contain supported claims.")
    return answer


def _no_match(question: str, provider: str, model: str, answer: str):
    return {
        "success": True,
        "provider": str(provider or "lifeos")[:30],
        "model": str(model or "module-answerability")[:100],
        "question": question,
        "answer": answer,
        "found_in_document": False,
        "claims": [],
    }


def _save_failed(module, lecture, user_id, question, fingerprint, error):
    try:
        config = get_ai_configuration()
        provider = str(config.get("provider") or "unknown")[:30]
        model = str(config.get("model") or "unknown")[:100]
    except AIServiceError:
        provider = model = "unavailable"
    row = ModuleQuestion(
        module_id=module.id,
        lecture_id=lecture.id if lecture is not None else None,
        user_id=user_id,
        question=question,
        answer=None,
        sources_json=None,
        provider=provider,
        model=model,
        status="Failed",
        source_fingerprint=fingerprint,
        error_message=str(error)[:2000],
    )
    try:
        db.session.add(row)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()

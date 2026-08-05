"""Tests for verified answerability in the document-question workflow."""

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from database import db
from models import Document, DocumentQuestion, Project
import services.document_question_workflow_service as workflow
from services.ai_service import AIServiceError
from services.document_answerability_service import (
    DocumentAnswerabilityProviderError,
)
from services.document_question_workflow_service import (
    DocumentQuestionNotFoundError,
    DocumentQuestionNotReadyError,
    DocumentQuestionWorkflowError,
    ask_owned_document,
)


@dataclass(frozen=True)
class FakeRetrievedChunk:
    page: int
    section: str
    evidence: str

    def source(self) -> dict:
        return {
            "page": self.page,
            "section": self.section,
            "evidence": self.evidence,
        }


def create_document(
    *,
    user_id: int,
    extracted_text: str | None,
) -> Document:
    project = Project(
        user_id=user_id,
        title="Document Question Project",
        status="In Progress",
        priority="High",
    )

    document = Document(
        project=project,
        filename="requirements.pdf",
        file_path="stored/requirements.pdf",
        extracted_text=extracted_text,
    )

    db.session.add_all(
        [project, document]
    )
    db.session.commit()

    return document


def build_fake_context(
    result,
    max_characters,
):
    """Build numbered source blocks from fake retrieved chunks."""

    blocks = []

    for source_id, retrieved_chunk in enumerate(
        result.chunks,
        start=1,
    ):
        source = retrieved_chunk.source()

        blocks.append(
            (
                f"[Source {source_id} | "
                f"Page {source['page']} | "
                f"{source['section']}]\n"
                f"{source['evidence']}"
            )
        )

    return "\n\n".join(blocks)[:max_characters]


def fake_verification(
    *,
    answerable=True,
    source_ids=(1,),
    confidence="high",
):
    return SimpleNamespace(
        answerable=answerable,
        confidence=confidence,
        reason=(
            "The sources directly answer the question."
            if answerable
            else "The requested information is absent."
        ),
        source_ids=tuple(source_ids),
        provider="gemini",
        model="test-verifier-model",
    )


def patch_retrieval(
    monkeypatch,
    *,
    chunks=None,
    verification=None,
):
    active_chunks = chunks or [
        FakeRetrievedChunk(
            page=1,
            section="Requirements",
            evidence=(
                "Secure document search is required."
            ),
        )
    ]

    result = SimpleNamespace(
        chunks=active_chunks
    )

    monkeypatch.setattr(
        workflow,
        "retrieve_owned_document_chunks_hybrid",
        lambda **kwargs: result,
    )

    monkeypatch.setattr(
        workflow,
        "build_hybrid_retrieval_context",
        build_fake_context,
    )

    active_verification = (
        verification
        if verification is not None
        else fake_verification()
    )

    monkeypatch.setattr(
        workflow,
        "verify_document_answerability",
        lambda **kwargs: active_verification,
    )


def fake_answer_result(
    *,
    claims=None,
    found_in_document=True,
):
    active_claims = claims

    if active_claims is None:
        active_claims = (
            [
                {
                    "text": (
                        "Secure document search is required."
                    ),
                    "source_ids": [1],
                }
            ]
            if found_in_document
            else []
        )

    return {
        "success": True,
        "provider": "gemini",
        "model": "test-answer-model",
        "question": "What is required?",
        "answer": (
            "Secure document search is required. [Source 1]"
            if found_in_document
            else "The information was not found."
        ),
        "found_in_document": found_in_document,
        "claims": active_claims,
        "input_characters": 100,
    }


def test_verifier_filters_sources_before_answer_generation(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable content.",
        )

        patch_retrieval(
            monkeypatch,
            chunks=[
                FakeRetrievedChunk(
                    1,
                    "Overview",
                    "General overview.",
                ),
                FakeRetrievedChunk(
                    2,
                    "Ownership",
                    "Ownership checks are required.",
                ),
                FakeRetrievedChunk(
                    3,
                    "Sessions",
                    "CSRF protection is required.",
                ),
            ],
            verification=fake_verification(
                source_ids=(2, 3),
            ),
        )

        captured = {}

        def fake_answer(**kwargs):
            captured["context"] = kwargs[
                "extracted_text"
            ]

            return fake_answer_result(
                claims=[
                    {
                        "text": (
                            "Ownership checks are required."
                        ),
                        "source_ids": [1],
                    },
                    {
                        "text": (
                            "CSRF protection is required."
                        ),
                        "source_ids": [2],
                    },
                ]
            )

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            fake_answer,
        )

        saved = ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="How is data protected?",
        )

        assert "General overview" not in captured["context"]
        assert "Ownership checks" in captured["context"]
        assert "CSRF protection" in captured["context"]

        assert [
            item["page"]
            for item in saved.question.sources
        ] == [2, 3]

        assert [
            item["source_id"]
            for item in saved.question.sources
        ] == [1, 2]


def test_unanswerable_verification_skips_answer_ai(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text=(
                "This document describes software architecture."
            ),
        )

        patch_retrieval(
            monkeypatch,
            verification=fake_verification(
                answerable=False,
                source_ids=(),
            ),
        )

        def fail_if_called(**kwargs):
            raise AssertionError(
                "Answer generation must not run for "
                "an unanswerable question."
            )

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            fail_if_called,
        )

        saved = ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text=(
                "What recipe should I cook tonight?"
            ),
        )

        assert saved.question.answer == workflow.NO_MATCH_ANSWER
        assert saved.question.sources == []
        assert saved.question.provider == "gemini"
        assert "answerability" in saved.question.model
        assert saved.question.status == "Completed"


def test_invalid_verifier_source_is_rejected(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable content.",
        )

        patch_retrieval(
            monkeypatch,
            verification=fake_verification(
                source_ids=(99,),
            ),
        )

        with pytest.raises(
            DocumentQuestionWorkflowError,
            match="not supplied by retrieval",
        ):
            ask_owned_document(
                document_id=document.id,
                user_id=user,
                question_text="What is required?",
            )


def test_verifier_failure_is_saved(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable content.",
        )

        patch_retrieval(monkeypatch)

        monkeypatch.setattr(
            workflow,
            "verify_document_answerability",
            lambda **kwargs: (_ for _ in ()).throw(
                DocumentAnswerabilityProviderError(
                    "Verifier provider unavailable."
                )
            ),
        )

        monkeypatch.setattr(
            workflow,
            "get_ai_configuration",
            lambda: {
                "provider": "gemini",
                "model": "test-model",
            },
        )

        with pytest.raises(
            DocumentQuestionWorkflowError,
            match="Verifier provider unavailable",
        ):
            ask_owned_document(
                document_id=document.id,
                user_id=user,
                question_text="What is required?",
            )

        failed = DocumentQuestion.query.filter_by(
            document_id=document.id,
            status="Failed",
        ).one()

        assert (
            "Verifier provider unavailable"
            in failed.error_message
        )


def test_invalid_claim_source_is_rejected_and_saved(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable content.",
        )

        patch_retrieval(monkeypatch)

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            lambda **kwargs: fake_answer_result(
                claims=[
                    {
                        "text": "Unsupported claim.",
                        "source_ids": [99],
                    }
                ]
            ),
        )

        monkeypatch.setattr(
            workflow,
            "get_ai_configuration",
            lambda: {
                "provider": "gemini",
                "model": "test-model",
            },
        )

        with pytest.raises(
            DocumentQuestionWorkflowError,
            match="source that was not supplied",
        ):
            ask_owned_document(
                document_id=document.id,
                user_id=user,
                question_text="What is required?",
            )

        failed = DocumentQuestion.query.filter_by(
            document_id=document.id,
            status="Failed",
        ).one()

        assert (
            "source that was not supplied"
            in failed.error_message
        )


def test_answer_model_not_found_saves_no_sources(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="General content.",
        )

        patch_retrieval(monkeypatch)

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            lambda **kwargs: fake_answer_result(
                found_in_document=False
            ),
        )

        saved = ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="Which fingerprint device?",
        )

        assert saved.question.sources == []
        assert (
            saved.question.answer
            == "The information was not found."
        )


def test_identical_question_is_reused(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable content.",
        )

        patch_retrieval(monkeypatch)

        calls = {
            "count": 0,
        }

        def fake_answer(**kwargs):
            calls["count"] += 1
            return fake_answer_result()

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            fake_answer,
        )

        first = ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="What is required?",
        )

        second = ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="What is required?",
        )

        assert first.reused_existing is False
        assert second.reused_existing is True
        assert calls["count"] == 1


def test_force_creates_fresh_answer(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable content.",
        )

        patch_retrieval(monkeypatch)

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            lambda **kwargs: fake_answer_result(),
        )

        first = ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="What is required?",
        )

        second = ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="What is required?",
            force=True,
        )

        assert first.question.id != second.question.id


def test_other_user_cannot_ask(app, user):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Private.",
        )

        with pytest.raises(
            DocumentQuestionNotFoundError
        ):
            ask_owned_document(
                document_id=document.id,
                user_id=user + 999,
                question_text="What is this?",
            )


def test_document_without_text_is_not_ready(app, user):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="",
        )

        with pytest.raises(
            DocumentQuestionNotReadyError
        ):
            ask_owned_document(
                document_id=document.id,
                user_id=user,
                question_text="What is this?",
            )


def test_empty_question_is_rejected(app, user):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable.",
        )

        with pytest.raises(
            DocumentQuestionWorkflowError
        ):
            ask_owned_document(
                document_id=document.id,
                user_id=user,
                question_text="   ",
            )


def test_answer_ai_failure_is_saved(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable.",
        )

        patch_retrieval(monkeypatch)

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            lambda **kwargs: (_ for _ in ()).throw(
                AIServiceError(
                    "Answer provider unavailable."
                )
            ),
        )

        monkeypatch.setattr(
            workflow,
            "get_ai_configuration",
            lambda: {
                "provider": "gemini",
                "model": "test-model",
            },
        )

        with pytest.raises(
            DocumentQuestionWorkflowError
        ):
            ask_owned_document(
                document_id=document.id,
                user_id=user,
                question_text="What is required?",
            )

        failed = DocumentQuestion.query.filter_by(
            status="Failed"
        ).one()

        assert (
            "Answer provider unavailable"
            in failed.error_message
        )



def capture_rag_events(
    monkeypatch,
):
    """Capture workflow log calls without writing real logs."""

    events: list[dict] = []

    monkeypatch.setattr(
        workflow,
        "create_document_rag_trace_id",
        lambda: "trace1234567890",
    )

    def fake_log(**kwargs):
        events.append(
            kwargs
        )
        return kwargs

    monkeypatch.setattr(
        workflow,
        "log_document_rag_event",
        fake_log,
    )

    return events


def _raise_answerability_error():
    """Raise a predictable verifier error for logging tests."""

    raise DocumentAnswerabilityProviderError(
        "Temporary provider failure."
    )


def test_successful_workflow_logs_all_main_stages(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable document content.",
        )

        events = capture_rag_events(
            monkeypatch
        )

        patch_retrieval(
            monkeypatch
        )

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            lambda **kwargs: fake_answer_result(),
        )

        ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="What is required?",
        )

        assert [
            event["event"]
            for event in events
        ] == [
            "question_started",
            "retrieval_completed",
            "answerability_completed",
            "answer_generation_completed",
            "question_saved",
        ]

        assert {
            event["trace_id"]
            for event in events
        } == {
            "trace1234567890"
        }


def test_unanswerable_workflow_skips_answer_generation_log(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Software architecture content.",
        )

        events = capture_rag_events(
            monkeypatch
        )

        patch_retrieval(
            monkeypatch,
            verification=fake_verification(
                answerable=False,
                source_ids=(),
            ),
        )

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            lambda **kwargs: pytest.fail(
                "Answer generation must not run."
            ),
        )

        ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="What recipe should I cook?",
        )

        event_names = [
            event["event"]
            for event in events
        ]

        assert event_names == [
            "question_started",
            "retrieval_completed",
            "answerability_completed",
            "question_saved",
        ]

        assert (
            "answer_generation_completed"
            not in event_names
        )


def test_reused_question_has_reuse_log(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable document content.",
        )

        events = capture_rag_events(
            monkeypatch
        )

        patch_retrieval(
            monkeypatch
        )

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            lambda **kwargs: fake_answer_result(),
        )

        ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="What is required?",
        )

        events.clear()

        reused = ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="What is required?",
        )

        assert reused.reused_existing is True

        assert [
            event["event"]
            for event in events
        ] == [
            "question_started",
            "question_reused",
        ]


def test_answerability_failure_is_logged(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable document content.",
        )

        events = capture_rag_events(
            monkeypatch
        )

        patch_retrieval(
            monkeypatch
        )

        monkeypatch.setattr(
            workflow,
            "verify_document_answerability",
            lambda **kwargs: (
                _raise_answerability_error()
            ),
        )

        monkeypatch.setattr(
            workflow,
            "get_ai_configuration",
            lambda: {
                "provider": "gemini",
                "model": "test-model",
            },
        )

        with pytest.raises(
            DocumentQuestionWorkflowError
        ):
            ask_owned_document(
                document_id=document.id,
                user_id=user,
                question_text="What is required?",
            )

        failure_events = [
            event
            for event in events
            if event["event"]
            == "workflow_failed"
        ]

        assert len(
            failure_events
        ) == 1

        assert failure_events[0][
            "stage"
        ] == "answerability"

        assert failure_events[0][
            "error_type"
        ] == (
            "DocumentAnswerabilityProviderError"
        )



def test_saved_source_uses_focused_evidence_preview():
    long_intro = (
        "This introductory material describes colors, layout and "
        "general navigation. "
    ) * 8

    relevant_sentence = (
        "Every project query is filtered by the current user "
        "identifier before records are returned."
    )

    source_text = (
        long_intro
        + relevant_sentence
        + " The remaining paragraph describes future design work."
    )

    retrieved_chunk = SimpleNamespace(
        text=source_text,
        matched_terms=(
            "project",
            "user",
            "records",
        ),
        source=lambda: {
            "page": 12,
            "section": "Ownership",
            "evidence": source_text[:420],
        },
    )

    retrieval_result = SimpleNamespace(
        query=(
            "How does LifeOS separate project records "
            "between users?"
        ),
        chunks=[
            retrieved_chunk
        ],
    )

    sources = workflow._sources_from_claims(
        retrieval_result=retrieval_result,
        claims=[
            {
                "text": (
                    "Project queries are filtered by the "
                    "current user identifier."
                ),
                "source_ids": [1],
            }
        ],
    )

    assert len(sources) == 1
    assert sources[0]["source_id"] == 1
    assert sources[0]["page"] == 12
    assert sources[0]["preview_type"] == "focused"
    assert relevant_sentence in sources[0]["evidence"]
    assert len(sources[0]["evidence"]) <= 420
    assert (
        "colors, layout"
        not in sources[0]["evidence"]
    )

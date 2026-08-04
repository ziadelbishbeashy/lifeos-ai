"""Tests for the persistent hybrid-RAG document-question workflow."""

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from database import db
from models import (
    Document,
    DocumentQuestion,
    Project,
)
import services.document_question_workflow_service as workflow
from services.ai_service import AIServiceError
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
        [
            project,
            document,
        ]
    )
    db.session.commit()

    return document


def patch_retrieval(
    monkeypatch,
    *,
    chunks: list[FakeRetrievedChunk] | None = None,
) -> None:
    active_chunks = chunks or [
        FakeRetrievedChunk(
            page=1,
            section="System Requirements",
            evidence=(
                "The system must support secure document search."
            ),
        )
    ]

    retrieval_result = SimpleNamespace(
        chunks=active_chunks,
    )

    monkeypatch.setattr(
        workflow,
        "retrieve_owned_document_chunks_hybrid",
        lambda **kwargs: retrieval_result,
    )

    monkeypatch.setattr(
        workflow,
        "build_hybrid_retrieval_context",
        lambda result, max_characters: (
            "[Source 1 | Page 1 | System Requirements]\n"
            "The system must support secure document search."
        ),
    )


def fake_answer_result(
    *,
    source_ids: list[int] | None = None,
    found_in_document: bool = True,
) -> dict:
    return {
        "success": True,
        "provider": "gemini",
        "model": "test-model",
        "question": "What must the system support?",
        "answer": (
            "The system must support secure document search."
            if found_in_document
            else "The information was not found."
        ),
        "found_in_document": found_in_document,
        "source_ids": (
            source_ids
            if source_ids is not None
            else ([1] if found_in_document else [])
        ),
        "input_characters": 200,
    }


def test_answer_saves_only_the_cited_retrieved_source(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\nGeneral overview.\n\n"
                "--- Page 2 ---\nSecure document search."
            ),
        )

        patch_retrieval(
            monkeypatch,
            chunks=[
                FakeRetrievedChunk(
                    page=1,
                    section="Overview",
                    evidence="General overview.",
                ),
                FakeRetrievedChunk(
                    page=2,
                    section="Security",
                    evidence="Secure document search is required.",
                ),
            ],
        )

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            lambda **kwargs: fake_answer_result(
                source_ids=[2]
            ),
        )

        saved = ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="What security is required?",
        )

        assert saved.reused_existing is False
        assert saved.question.status == "Completed"
        assert len(saved.question.sources) == 1
        assert saved.question.sources[0]["page"] == 2
        assert (
            saved.question.sources[0]["section"]
            == "Security"
        )


def test_identical_question_is_reused(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "The system must support secure document search."
            ),
        )

        patch_retrieval(monkeypatch)

        call_count = {"value": 0}

        def fake_ask(**kwargs):
            call_count["value"] += 1
            return fake_answer_result()

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            fake_ask,
        )

        first = ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="What must the system support?",
        )

        second = ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="What must the system support?",
        )

        assert first.reused_existing is False
        assert second.reused_existing is True
        assert second.question.id == first.question.id
        assert call_count["value"] == 1


def test_force_creates_a_fresh_answer(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "The system must support secure document search."
            ),
        )

        patch_retrieval(monkeypatch)

        call_count = {"value": 0}

        def fake_ask(**kwargs):
            call_count["value"] += 1
            return fake_answer_result()

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            fake_ask,
        )

        first = ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="What must the system support?",
        )

        second = ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="What must the system support?",
            force=True,
        )

        assert first.question.id != second.question.id
        assert second.reused_existing is False
        assert call_count["value"] == 2


def test_other_user_cannot_ask_about_document(
    app,
    user,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable private document.",
        )

        with pytest.raises(
            DocumentQuestionNotFoundError,
            match="not found",
        ):
            ask_owned_document(
                document_id=document.id,
                user_id=user + 9999,
                question_text="What does it contain?",
            )


def test_document_without_text_is_not_ready(
    app,
    user,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="",
        )

        with pytest.raises(
            DocumentQuestionNotReadyError,
            match="no readable",
        ):
            ask_owned_document(
                document_id=document.id,
                user_id=user,
                question_text="What does it contain?",
            )


def test_empty_question_is_rejected(
    app,
    user,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable document content.",
        )

        with pytest.raises(
            DocumentQuestionWorkflowError,
            match="Enter a question",
        ):
            ask_owned_document(
                document_id=document.id,
                user_id=user,
                question_text="   ",
            )


def test_ai_failure_is_saved(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "The system must support secure document search."
            ),
        )

        patch_retrieval(monkeypatch)

        def fail_question(**kwargs):
            raise AIServiceError(
                "The AI provider is unavailable."
            )

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            fail_question,
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
            match="provider is unavailable",
        ):
            ask_owned_document(
                document_id=document.id,
                user_id=user,
                question_text="What must the system support?",
            )

        failed = DocumentQuestion.query.filter_by(
            document_id=document.id,
            user_id=user,
            status="Failed",
        ).one()

        assert failed.answer is None
        assert failed.provider == "gemini"
        assert failed.model == "test-model"
        assert "provider is unavailable" in failed.error_message


def test_invalid_source_id_is_rejected_and_saved(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "The system must support secure document search."
            ),
        )

        patch_retrieval(monkeypatch)

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            lambda **kwargs: fake_answer_result(
                source_ids=[99]
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
                question_text="What must the system support?",
            )

        failed = DocumentQuestion.query.filter_by(
            document_id=document.id,
            user_id=user,
            status="Failed",
        ).one()

        assert "source that was not supplied" in (
            failed.error_message
        )


def test_not_found_answer_saves_no_sources(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="General project content.",
        )

        patch_retrieval(monkeypatch)

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            lambda **kwargs: fake_answer_result(
                found_in_document=False,
                source_ids=[],
            ),
        )

        saved = ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="Which fingerprint device is required?",
        )

        assert saved.question.status == "Completed"
        assert saved.question.sources == []
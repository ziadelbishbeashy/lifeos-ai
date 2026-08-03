"""Tests for the persistent document-question workflow."""

import pytest

from database import db
from models import (
    Document,
    DocumentQuestion,
    Project,
)
from services.ai_service import AIServiceError
from services import (
    document_question_workflow_service as workflow,
)
from services.document_question_workflow_service import (
    DocumentQuestionNotFoundError,
    DocumentQuestionNotReadyError,
    DocumentQuestionWorkflowError,
    ask_owned_document,
    list_owned_document_questions,
)


def create_document(
    *,
    user_id: int,
    extracted_text: str | None,
) -> Document:
    project = Project(
        user_id=user_id,
        title="Document Questions",
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


def fake_answer_result():
    return {
        "success": True,
        "provider": "gemini",
        "model": "test-model",
        "question": "What must the system support?",
        "answer": (
            "The system must support grounded "
            "document questions."
        ),
        "found_in_document": True,
        "sources": [
            {
                "page": 3,
                "section": "Requirements",
                "evidence": (
                    "The system must support "
                    "document questions."
                ),
            }
        ],
        "input_characters": 100,
    }


def test_owned_document_question_is_saved(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text=(
                "--- Page 3 ---\n"
                "The system must support document questions."
            ),
        )

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            lambda **kwargs: fake_answer_result(),
        )

        result = ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text=(
                "What must the system support?"
            ),
        )

        assert result.reused_existing is False
        assert result.question.status == "Completed"
        assert result.question.provider == "gemini"
        assert result.question.model == "test-model"
        assert result.question.sources[0]["page"] == 3

        saved = db.session.get(
            DocumentQuestion,
            result.question.id,
        )

        assert saved is not None
        assert saved.answer.startswith(
            "The system must support"
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
                "System Requirements\n"
                "The system must support secure document "
                "search and project ownership validation."
            ),
        )

        call_count = {
            "value": 0,
        }

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
            question_text=(
                "What must the system support?"
            ),
        )

        second = ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text=(
                "What must the system support?"
            ),
        )

        assert first.reused_existing is False
        assert second.reused_existing is True
        assert second.question.id == first.question.id
        assert call_count["value"] == 1


def test_force_creates_new_answer(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Stable readable content.",
        )

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
        assert second.reused_existing is False


def test_other_users_document_is_blocked(
    app,
    user,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable content.",
        )

        with pytest.raises(
            DocumentQuestionNotFoundError,
            match="not found",
        ):
            ask_owned_document(
                document_id=document.id,
                user_id=user + 9999,
                question_text="What is mentioned?",
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
            match="no readable extracted text",
        ):
            ask_owned_document(
                document_id=document.id,
                user_id=user,
                question_text="What is mentioned?",
            )


def test_empty_question_is_rejected(
    app,
    user,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable content.",
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
                "System Requirements\n"
                "The system must support secure document "
                "search and project ownership validation."
            ),
        )

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
                question_text=(
                    "What must the system support?"
                ),
            )

        failed_question = (
            DocumentQuestion.query
            .filter_by(
                document_id=document.id,
                user_id=user,
                status="Failed",
            )
            .one()
        )

        assert failed_question.answer is None
        assert failed_question.provider == "gemini"
        assert failed_question.model == "test-model"

        assert (
            "provider is unavailable"
            in failed_question.error_message
        )

def test_question_history_is_returned(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable content.",
        )

        monkeypatch.setattr(
            workflow,
            "ask_document_question",
            lambda **kwargs: fake_answer_result(),
        )

        ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="First question?",
        )

        ask_owned_document(
            document_id=document.id,
            user_id=user,
            question_text="Second question?",
        )

        history = list_owned_document_questions(
            document_id=document.id,
            user_id=user,
        )

        assert len(history) == 2
        assert history[0].question == "Second question?"
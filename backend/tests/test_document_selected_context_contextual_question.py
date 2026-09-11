"""Regression tests for contextual highlighted-PDF questions."""

from types import SimpleNamespace

from services import document_question_workflow_service as workflow
from services.document_selected_context_service import (
    ValidatedDocumentSelection,
)


def make_selection():
    return ValidatedDocumentSelection(
        document=SimpleNamespace(
            id=12
        ),
        text=(
            "The system verifies ownership before returning "
            "private project information."
        ),
        page=8,
        section="Privacy",
    )


def test_model_question_resolves_this_to_selected_source():
    question = workflow._build_model_question(
        question="Explain this in simple terms.",
        selected_context=make_selection(),
    )

    assert "highlighted Source 1" in question
    assert '"this"' in question
    assert "Source 1 itself is direct evidence" in question
    assert "Explain this in simple terms." in question


def test_model_question_keeps_plain_questions_unchanged():
    original = "What is the project deadline?"

    question = workflow._build_model_question(
        question=original,
        selected_context=None,
    )

    assert question == original


def test_selected_context_workflow_version_invalidates_old_no_answer_cache():
    assert (
        workflow.QUESTION_WORKFLOW_VERSION
        == "document-question-selected-context-v11"
    )

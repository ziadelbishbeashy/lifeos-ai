"""Regression tests for Step 8D selected-context answering."""

from types import SimpleNamespace

from services import document_question_workflow_service as workflow
from services.document_hybrid_retrieval_service import (
    build_hybrid_retrieval_context,
)
from services.document_selected_context_service import (
    ValidatedDocumentSelection,
)


def make_selection():
    return ValidatedDocumentSelection(
        document=SimpleNamespace(id=12),
        text=(
            "The system verifies project ownership before "
            "returning private project data."
        ),
        page=8,
        section="Privacy",
    )


def test_contextual_retrieval_query_contains_question_and_selection():
    query = workflow._build_question_retrieval_query(
        question="Why is this important?",
        selected_context=make_selection(),
    )

    assert "Why is this important?" in query
    assert "verifies project ownership" in query


def test_exact_selected_text_is_always_first_answer_source():
    selection = make_selection()

    unrelated_chunk = SimpleNamespace(
        id=91,
        document_id=12,
        chunk_index=20,
        page_start=15,
        page_end=15,
        section_title="Other",
        text="Another passage elsewhere in the document.",
    )

    normal_result = SimpleNamespace(
        chunks=[
            SimpleNamespace(
                chunk=unrelated_chunk,
                text=unrelated_chunk.text,
            )
        ],
        query="Why is this important?",
    )

    updated = workflow._prefer_selected_context_chunks(
        retrieval_result=normal_result,
        selected_context=selection,
        preferred_chunks=[],
    )

    assert updated.chunks[0].text == selection.text
    assert updated.chunks[0].page_start == 8
    assert updated.chunks[0].chunk.context_role == "selected"


def test_selected_text_is_in_answerability_context_even_without_chunk_mapping():
    selection = make_selection()

    normal_result = SimpleNamespace(
        chunks=[],
        query="Explain this.",
    )

    updated = workflow._prefer_selected_context_chunks(
        retrieval_result=normal_result,
        selected_context=selection,
        preferred_chunks=[],
    )

    context = build_hybrid_retrieval_context(
        updated,
        max_characters=14000,
    )

    assert "[Source 1 | Page 8 | Privacy]" in context
    assert "verifies project ownership" in context


def test_old_no_answer_cache_is_invalidated_by_workflow_version():
    assert (
        workflow.QUESTION_WORKFLOW_VERSION
        == "document-question-selected-context-v11"
    )

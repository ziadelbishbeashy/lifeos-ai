"""Compatibility regressions for the Step 8D selected-context fixes."""

from types import SimpleNamespace

from services import document_question_workflow_service as workflow


def test_preferred_chunk_helper_still_supports_old_call_shape():
    preferred_chunk = SimpleNamespace(
        id=22,
        document_id=1,
        chunk_index=4,
        page_start=8,
        page_end=8,
        section_title="Privacy",
        text="Selected context.",
    )

    normal_chunk = SimpleNamespace(
        id=33,
        document_id=1,
        chunk_index=8,
        page_start=12,
        page_end=12,
        section_title="Authentication",
        text="Retrieved supporting context.",
    )

    normal_retrieved = SimpleNamespace(
        chunk=normal_chunk,
        text=normal_chunk.text,
    )

    result = SimpleNamespace(
        chunks=[normal_retrieved],
        query="Why is this important?",
    )

    updated = workflow._prefer_selected_context_chunks(
        retrieval_result=result,
        preferred_chunks=[preferred_chunk],
    )

    assert updated.chunks[0].chunk.id == 22
    assert updated.chunks[1].chunk.id == 33

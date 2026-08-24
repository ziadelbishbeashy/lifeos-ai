"""Tests for privacy-safe Document Brain RAG logging."""

import json
from types import SimpleNamespace

import pytest

from services.document_rag_logging_service import (
    build_document_rag_event,
    build_retrieval_log_summary,
    create_document_rag_trace_id,
    create_question_fingerprint,
)


def test_trace_id_is_compact_and_unique():
    first = create_document_rag_trace_id()
    second = create_document_rag_trace_id()

    assert len(first) == 16
    assert len(second) == 16
    assert first != second


def test_question_fingerprint_is_stable():
    first = create_question_fingerprint(
        "How is private data protected?"
    )

    second = create_question_fingerprint(
        "  How   is private data protected?  "
    )

    assert first == second
    assert len(first) == 16


def test_event_does_not_include_raw_question():
    raw_question = (
        "How is one student's private data protected?"
    )

    payload = build_document_rag_event(
        event="retrieval_completed",
        trace_id="trace123",
        document_id=2,
        question=raw_question,
        candidate_count=5,
    )

    serialized = json.dumps(
        payload
    )

    assert raw_question not in serialized
    assert "question" not in payload
    assert payload[
        "question_characters"
    ] == len(raw_question)
    assert payload[
        "question_fingerprint"
    ]


def test_sensitive_log_fields_are_rejected():
    with pytest.raises(
        ValueError,
        match="Sensitive Document RAG log fields",
    ):
        build_document_rag_event(
            event="answer_completed",
            trace_id="trace123",
            document_id=2,
            answer="Private document content.",
        )


def test_retrieval_summary_contains_metadata_only():
    database_chunk = SimpleNamespace(
        id=15,
        chunk_index=4,
        page_start=8,
        page_end=8,
        text="Secret document text.",
    )

    retrieved_chunk = SimpleNamespace(
        chunk=database_chunk,
        page_start=8,
        page_end=8,
        score=0.0162,
        keyword_score=3.4,
        semantic_score=0.72,
        keyword_rank=1,
        semantic_rank=2,
        matched_terms=(
            "private",
            "data",
        ),
    )

    retrieval_result = SimpleNamespace(
        chunks=[
            retrieved_chunk
        ],
        mode="hybrid",
        keyword_result_count=4,
        semantic_result_count=5,
        index_rebuilt=False,
        chunks_rebuilt=False,
        embedded_count=0,
        reused_count=57,
        semantic_error=None,
    )

    summary = build_retrieval_log_summary(
        retrieval_result
    )

    serialized = json.dumps(
        summary
    )

    assert summary[
        "retrieval_mode"
    ] == "hybrid"

    assert summary[
        "candidate_count"
    ] == 1

    assert summary[
        "candidates"
    ][0]["chunk_id"] == 15

    assert summary[
        "candidates"
    ][0]["matched_term_count"] == 2

    assert "Secret document text." not in serialized
    assert "private" not in serialized
    assert "data" not in serialized


def test_nested_sensitive_fields_are_rejected():
    with pytest.raises(
        ValueError,
        match="Sensitive Document RAG log fields",
    ):
        build_document_rag_event(
            event="retrieval_completed",
            trace_id="trace123",
            document_id=2,
            retrieval={
                "candidate_count": 5,
                "evidence": "Sensitive excerpt.",
            },
        )
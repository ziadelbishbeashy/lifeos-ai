"""Privacy-safe structured logging for Document Brain RAG."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any

from flask import (
    current_app,
    has_app_context,
)


LOG_PREFIX = "lifeos.document_rag"

MAX_LOG_STRING_CHARACTERS = 300
MAX_LOG_LIST_ITEMS = 12

BLOCKED_FIELD_NAMES = {
    "answer",
    "chunk_text",
    "content",
    "evidence",
    "extracted_text",
    "question",
    "retrieved_context",
    "text",
}


def create_document_rag_trace_id() -> str:
    """Return a compact ID connecting one RAG workflow's logs."""

    return uuid.uuid4().hex[:16]


def create_question_fingerprint(
    question: str,
) -> str:
    """
    Return a non-reversible identifier for a question.

    The raw question is never written to application logs.
    """

    cleaned_question = " ".join(
        str(question or "").split()
    )

    return hashlib.sha256(
        cleaned_question.encode(
            "utf-8"
        )
    ).hexdigest()[:16]


def build_retrieval_log_summary(
    retrieval_result: Any,
) -> dict[str, Any]:
    """
    Return safe retrieval metadata without document text.

    Scores and ranking metadata are useful for debugging.
    Chunk contents and matched words are intentionally excluded.
    """

    retrieved_chunks = list(
        getattr(
            retrieval_result,
            "chunks",
            [],
        )
        or []
    )

    candidates: list[dict[str, Any]] = []

    for source_id, retrieved_chunk in enumerate(
        retrieved_chunks,
        start=1,
    ):
        chunk = getattr(
            retrieved_chunk,
            "chunk",
            None,
        )

        candidates.append(
            {
                "source_id": source_id,
                "chunk_id": getattr(
                    chunk,
                    "id",
                    None,
                ),
                "chunk_index": getattr(
                    chunk,
                    "chunk_index",
                    None,
                ),
                "page_start": _first_available(
                    getattr(
                        retrieved_chunk,
                        "page_start",
                        None,
                    ),
                    getattr(
                        chunk,
                        "page_start",
                        None,
                    ),
                ),
                "page_end": _first_available(
                    getattr(
                        retrieved_chunk,
                        "page_end",
                        None,
                    ),
                    getattr(
                        chunk,
                        "page_end",
                        None,
                    ),
                ),
                "hybrid_score": getattr(
                    retrieved_chunk,
                    "score",
                    None,
                ),
                "keyword_score": getattr(
                    retrieved_chunk,
                    "keyword_score",
                    None,
                ),
                "semantic_score": getattr(
                    retrieved_chunk,
                    "semantic_score",
                    None,
                ),
                "keyword_rank": getattr(
                    retrieved_chunk,
                    "keyword_rank",
                    None,
                ),
                "semantic_rank": getattr(
                    retrieved_chunk,
                    "semantic_rank",
                    None,
                ),
                "matched_term_count": len(
                    tuple(
                        getattr(
                            retrieved_chunk,
                            "matched_terms",
                            (),
                        )
                        or ()
                    )
                ),
            }
        )

    return {
        "retrieval_mode": getattr(
            retrieval_result,
            "mode",
            "unknown",
        ),
        "candidate_count": len(
            retrieved_chunks
        ),
        "keyword_result_count": getattr(
            retrieval_result,
            "keyword_result_count",
            None,
        ),
        "semantic_result_count": getattr(
            retrieval_result,
            "semantic_result_count",
            None,
        ),
        "index_rebuilt": bool(
            getattr(
                retrieval_result,
                "index_rebuilt",
                False,
            )
        ),
        "chunks_rebuilt": bool(
            getattr(
                retrieval_result,
                "chunks_rebuilt",
                False,
            )
        ),
        "embedded_count": getattr(
            retrieval_result,
            "embedded_count",
            None,
        ),
        "reused_embedding_count": getattr(
            retrieval_result,
            "reused_count",
            None,
        ),
        "semantic_error_present": bool(
            getattr(
                retrieval_result,
                "semantic_error",
                None,
            )
        ),
        "candidates": candidates,
    }


def build_document_rag_event(
    *,
    event: str,
    trace_id: str,
    document_id: int,
    question: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Build one privacy-safe structured log payload."""

    cleaned_event = str(
        event or ""
    ).strip()

    if not cleaned_event:
        raise ValueError(
            "A Document RAG log event must have a name."
        )

    _reject_sensitive_fields(
        fields
    )

    payload: dict[str, Any] = {
        "event": cleaned_event,
        "trace_id": str(
            trace_id or ""
        )[:32],
        "document_id": int(
            document_id
        ),
    }

    if question is not None:
        cleaned_question = " ".join(
            str(question or "").split()
        )

        payload.update(
            {
                "question_fingerprint": (
                    create_question_fingerprint(
                        cleaned_question
                    )
                ),
                "question_characters": len(
                    cleaned_question
                ),
            }
        )

    for field_name, field_value in fields.items():
        payload[field_name] = _make_json_safe(
            field_value
        )

    return payload


def log_document_rag_event(
    *,
    event: str,
    trace_id: str,
    document_id: int,
    question: str | None = None,
    level: str = "info",
    **fields: Any,
) -> dict[str, Any]:
    """
    Write one structured Document Brain log event.

    The payload is also returned to simplify testing.
    """

    payload = build_document_rag_event(
        event=event,
        trace_id=trace_id,
        document_id=document_id,
        question=question,
        **fields,
    )

    logger = (
        current_app.logger
        if has_app_context()
        else logging.getLogger(
            "lifeos.document_rag"
        )
    )

    safe_level = str(
        level or "info"
    ).lower()

    if safe_level not in {
        "debug",
        "info",
        "warning",
        "error",
        "critical",
    }:
        safe_level = "info"

    log_method = getattr(
        logger,
        safe_level,
    )

    log_method(
        "%s %s",
        LOG_PREFIX,
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        ),
    )

    return payload


def _reject_sensitive_fields(
    fields: dict[str, Any],
) -> None:
    """Prevent callers from accidentally logging document data."""

    blocked = {
        str(field_name).lower()
        for field_name in fields
        if str(field_name).lower()
        in BLOCKED_FIELD_NAMES
    }

    if blocked:
        blocked_names = ", ".join(
            sorted(
                blocked
            )
        )

        raise ValueError(
            "Sensitive Document RAG log fields are blocked: "
            f"{blocked_names}."
        )


def _make_json_safe(
    value: Any,
) -> Any:
    """Convert supported values into bounded JSON-safe data."""

    if value is None or isinstance(
        value,
        (
            bool,
            int,
            float,
        ),
    ):
        return value

    if isinstance(
        value,
        str,
    ):
        return value[
            :MAX_LOG_STRING_CHARACTERS
        ]

    if isinstance(
        value,
        dict,
    ):
        _reject_sensitive_fields(
            value
        )

        return {
            str(key): _make_json_safe(
                nested_value
            )
            for key, nested_value in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            _make_json_safe(
                item
            )
            for item in list(
                value
            )[:MAX_LOG_LIST_ITEMS]
        ]

    return str(
        value
    )[:MAX_LOG_STRING_CHARACTERS]


def _first_available(
    first: Any,
    second: Any,
) -> Any:
    """Return the first value unless it is missing."""

    return (
        first
        if first is not None
        else second
    )
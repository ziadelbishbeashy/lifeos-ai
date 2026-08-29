"""Central Step 20 resource and AI-cost limits for LifeOS.

The service intentionally controls *inputs and provider work*, not answer quality.
It does not create another RAG path. Existing Document Brain services keep their
retrieval/grounding behaviour while consulting one predictable limit policy.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

try:  # Keep the module usable by lightweight/static tooling.
    from flask import current_app, has_app_context, has_request_context, request
except Exception:  # pragma: no cover - Flask is an application dependency.
    current_app = None  # type: ignore[assignment]

    def has_app_context() -> bool:
        return False

    def has_request_context() -> bool:
        return False

    request = None  # type: ignore[assignment]


DEFAULT_MAX_UPLOAD_SIZE_MB = 25
DEFAULT_MAX_PDF_PAGES = 300
DEFAULT_MAX_EXTRACTED_TEXT_CHARACTERS = 200_000
DEFAULT_MAX_CHUNKS_PER_DOCUMENT = 250
DEFAULT_MAX_SCOPE_DOCUMENTS = 50
DEFAULT_MAX_RETRIEVAL_RESULTS = 12
DEFAULT_MAX_RAG_CONTEXT_CHARACTERS = 20_000
DEFAULT_MAX_AI_PROMPT_CHARACTERS = 120_000
DEFAULT_MAX_GENERATION_CALLS_PER_REQUEST = 4
DEFAULT_MAX_EMBEDDING_BATCH_SIZE = 50
DEFAULT_MAX_EMBEDDING_CALLS_PER_REQUEST = 12
DEFAULT_MAX_EMBEDDING_CHARACTERS_PER_REQUEST = 120_000


class ResourceLimitError(RuntimeError):
    """Raised when one LifeOS operation exceeds a configured resource boundary."""


@dataclass(frozen=True)
class ResourceLimits:
    max_upload_bytes: int
    max_pdf_pages: int
    max_extracted_text_characters: int
    max_chunks_per_document: int
    max_scope_documents: int
    max_retrieval_results: int
    max_rag_context_characters: int
    max_ai_prompt_characters: int
    max_generation_calls_per_request: int
    max_embedding_batch_size: int
    max_embedding_calls_per_request: int
    max_embedding_characters_per_request: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_resource_limits() -> ResourceLimits:
    """Return the active Step 20 policy from Flask config or environment.

    Flask config wins when an application context exists so tests and deployments
    can override limits without mutating process environment variables.
    """

    upload_mb = _int_value(
        "MAX_UPLOAD_SIZE_MB", DEFAULT_MAX_UPLOAD_SIZE_MB, minimum=1
    )
    max_content_length = _config_value("MAX_CONTENT_LENGTH")
    if max_content_length not in (None, ""):
        try:
            upload_bytes = max(1, int(max_content_length))
        except (TypeError, ValueError):
            upload_bytes = upload_mb * 1024 * 1024
    else:
        upload_bytes = upload_mb * 1024 * 1024

    return ResourceLimits(
        max_upload_bytes=upload_bytes,
        max_pdf_pages=_int_value("MAX_PDF_PAGES", DEFAULT_MAX_PDF_PAGES, minimum=1),
        max_extracted_text_characters=_int_value(
            "MAX_EXTRACTED_TEXT_CHARACTERS",
            DEFAULT_MAX_EXTRACTED_TEXT_CHARACTERS,
            minimum=10_000,
        ),
        max_chunks_per_document=_int_value(
            "MAX_CHUNKS_PER_DOCUMENT", DEFAULT_MAX_CHUNKS_PER_DOCUMENT, minimum=10
        ),
        max_scope_documents=_int_value(
            "MAX_SCOPE_DOCUMENTS", DEFAULT_MAX_SCOPE_DOCUMENTS, minimum=1
        ),
        max_retrieval_results=_bounded_int(
            "MAX_RETRIEVAL_RESULTS",
            DEFAULT_MAX_RETRIEVAL_RESULTS,
            minimum=1,
            maximum=12,
        ),
        max_rag_context_characters=_int_value(
            "MAX_RAG_CONTEXT_CHARACTERS",
            DEFAULT_MAX_RAG_CONTEXT_CHARACTERS,
            minimum=500,
        ),
        max_ai_prompt_characters=_int_value(
            "MAX_AI_PROMPT_CHARACTERS",
            DEFAULT_MAX_AI_PROMPT_CHARACTERS,
            minimum=2_000,
        ),
        max_generation_calls_per_request=_int_value(
            "AI_MAX_GENERATION_CALLS_PER_REQUEST",
            DEFAULT_MAX_GENERATION_CALLS_PER_REQUEST,
            minimum=1,
        ),
        max_embedding_batch_size=_bounded_int(
            "MAX_EMBEDDING_BATCH_SIZE",
            DEFAULT_MAX_EMBEDDING_BATCH_SIZE,
            minimum=1,
            maximum=100,
        ),
        max_embedding_calls_per_request=_int_value(
            "AI_MAX_EMBEDDING_CALLS_PER_REQUEST",
            DEFAULT_MAX_EMBEDDING_CALLS_PER_REQUEST,
            minimum=1,
        ),
        max_embedding_characters_per_request=_int_value(
            "AI_MAX_EMBEDDING_CHARACTERS_PER_REQUEST",
            DEFAULT_MAX_EMBEDDING_CHARACTERS_PER_REQUEST,
            minimum=1_000,
        ),
    )


def effective_context_limit(requested: int) -> int:
    """Clamp a workflow-specific context budget to the global Step 20 ceiling."""

    try:
        value = int(requested)
    except (TypeError, ValueError) as error:
        raise ResourceLimitError("The retrieval context limit is invalid.") from error
    if value < 500:
        raise ResourceLimitError(
            "Retrieval context must allow at least 500 characters."
        )
    return min(value, get_resource_limits().max_rag_context_characters)


def enforce_scope_document_count(count: int, *, scope_label: str) -> None:
    limit = get_resource_limits().max_scope_documents
    try:
        value = int(count)
    except (TypeError, ValueError) as error:
        raise ResourceLimitError("The workspace document count is invalid.") from error
    if value > limit:
        label = "workspace" if not str(scope_label or "").strip() else str(scope_label).strip()
        raise ResourceLimitError(
            f"This {label} contains {value} documents. LifeOS can search at most "
            f"{limit} documents in one AI request. Narrow the scope or split it into smaller Collections."
        )


def enforce_chunk_count(count: int) -> None:
    limit = get_resource_limits().max_chunks_per_document
    if int(count) > limit:
        raise ResourceLimitError(
            f"This document would create more than {limit} searchable chunks. "
            "Reduce the document size or increase the reviewed Step 20 limit."
        )


def guard_generation_request(*, provider: str, model: str, prompt: str) -> int:
    """Enforce prompt size and per-HTTP-request generation-call budget.

    Returns the 1-based call index for logging. Provider failures still consume a
    call because they represent real attempted external work. CLI evaluation is
    intentionally not counted as one HTTP request, but prompt-size limits still
    apply there.
    """

    limits = get_resource_limits()
    prompt_characters = len(str(prompt or ""))
    if prompt_characters > limits.max_ai_prompt_characters:
        raise ResourceLimitError(
            "The AI request is too large for the configured LifeOS provider budget. "
            f"Maximum prompt size is {limits.max_ai_prompt_characters:,} characters."
        )

    call_index = 1
    if has_request_context() and request is not None:
        # Flask's ``g`` is application-context scoped, so it can survive across
        # multiple request contexts when tests or internal workflows keep one
        # app context open. Step 20 budgets are explicitly per HTTP request, so
        # store counters on this request's WSGI environ instead.
        environ = request.environ
        previous = int(environ.get("lifeos.generation_call_count", 0) or 0)
        call_index = previous + 1
        if call_index > limits.max_generation_calls_per_request:
            raise ResourceLimitError(
                "This request reached the configured LifeOS AI-call budget. "
                "Please finish the current operation and start a new request."
            )
        environ["lifeos.generation_call_count"] = call_index

    _log_provider_attempt(
        provider=provider,
        model=model,
        prompt_characters=prompt_characters,
        call_index=call_index,
    )
    return call_index



def guard_embedding_request(*, provider: str, model: str, texts: list[str]) -> int:
    """Bound embedding provider work per HTTP request while preserving reuse.

    Existing embeddings cost nothing here because this guard is reached only for
    actual provider calls. If the budget is exhausted, retrieval services already
    have their established keyword fallback path.
    """

    limits = get_resource_limits()
    characters = sum(len(str(text or "")) for text in texts)
    call_index = 1
    total_characters = characters

    if has_request_context() and request is not None:
        environ = request.environ
        previous_calls = int(environ.get("lifeos.embedding_call_count", 0) or 0)
        previous_characters = int(
            environ.get("lifeos.embedding_character_count", 0) or 0
        )
        call_index = previous_calls + 1
        total_characters = previous_characters + characters
        if call_index > limits.max_embedding_calls_per_request:
            raise ResourceLimitError(
                "This request reached the configured LifeOS embedding-call budget. "
                "Keyword retrieval remains available; semantic indexing can continue later."
            )
        if total_characters > limits.max_embedding_characters_per_request:
            raise ResourceLimitError(
                "This request reached the configured LifeOS embedding-input budget. "
                "Keyword retrieval remains available; semantic indexing can continue later."
            )
        environ["lifeos.embedding_call_count"] = call_index
        environ["lifeos.embedding_character_count"] = total_characters

    _log_provider_attempt(
        provider=provider,
        model=model,
        prompt_characters=characters,
        call_index=call_index,
        operation="embedding",
    )
    return call_index

def format_resource_limits_summary(limits: ResourceLimits | None = None) -> str:
    active = limits or get_resource_limits()
    rows = [
        "Step 20 Resource Limits",
        f"max_upload_mb={active.max_upload_bytes / (1024 * 1024):g}",
        f"max_pdf_pages={active.max_pdf_pages}",
        f"max_extracted_text_characters={active.max_extracted_text_characters}",
        f"max_chunks_per_document={active.max_chunks_per_document}",
        f"max_scope_documents={active.max_scope_documents}",
        f"max_retrieval_results={active.max_retrieval_results}",
        f"max_rag_context_characters={active.max_rag_context_characters}",
        f"max_ai_prompt_characters={active.max_ai_prompt_characters}",
        f"max_generation_calls_per_request={active.max_generation_calls_per_request}",
        f"max_embedding_batch_size={active.max_embedding_batch_size}",
        f"max_embedding_calls_per_request={active.max_embedding_calls_per_request}",
        f"max_embedding_characters_per_request={active.max_embedding_characters_per_request}",
    ]
    return "\n".join(rows)


def _config_value(name: str):
    if has_app_context() and current_app is not None:
        value = current_app.config.get(name)
        if value is not None:
            return value
    return os.getenv(name)


def _int_value(name: str, default: int, *, minimum: int) -> int:
    raw = _config_value(name)
    try:
        value = int(raw) if raw not in (None, "") else int(default)
    except (TypeError, ValueError):
        value = int(default)
    return max(minimum, value)


def _bounded_int(
    name: str, default: int, *, minimum: int, maximum: int
) -> int:
    return min(maximum, _int_value(name, default, minimum=minimum))


def _log_provider_attempt(
    *,
    provider: str,
    model: str,
    prompt_characters: int,
    call_index: int,
    operation: str = "generation",
) -> None:
    if not has_app_context() or current_app is None:
        return
    current_app.logger.info(
        "lifeos.ai_usage operation=%s provider=%s model=%s input_characters=%s request_call=%s",
        str(operation or "unknown")[:30],
        str(provider or "unknown")[:30],
        str(model or "unknown")[:100],
        int(prompt_characters),
        int(call_index),
    )

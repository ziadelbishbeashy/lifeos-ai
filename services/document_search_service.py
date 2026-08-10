"""Search inside an owned PDF using exact, keyword, and semantic retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from services.document_chunk_service import (
    DocumentChunkError,
    DocumentChunkNotFoundError,
    DocumentChunkNotReadyError,
    ensure_owned_document_chunks,
)
from services.document_evidence_preview_service import (
    build_focused_evidence_preview,
)
from services.document_hybrid_retrieval_service import (
    DocumentHybridRetrievalError,
    DocumentHybridRetrievalNotFoundError,
    DocumentHybridRetrievalNotReadyError,
    DocumentHybridRetrievalValidationError,
    retrieve_owned_document_chunks_hybrid,
)


DEFAULT_SEARCH_RESULT_LIMIT = 8
MAX_SEARCH_RESULT_LIMIT = 12
MAX_SEARCH_QUERY_CHARACTERS = 500
SEARCH_PREVIEW_CHARACTERS = 460

PAGE_MARKER_PATTERN = re.compile(
    r"^--- Page\s+\d+\s+---\s*",
    flags=re.MULTILINE,
)


class DocumentSearchError(RuntimeError):
    """Base error for direct document search."""


class DocumentSearchNotFoundError(DocumentSearchError):
    """Raised when a document is missing or not owned."""


class DocumentSearchNotReadyError(DocumentSearchError):
    """Raised when a document has no searchable text."""


class DocumentSearchValidationError(DocumentSearchError):
    """Raised when a search query is invalid."""


@dataclass(frozen=True)
class DocumentSearchHit:
    """One real document passage returned to the user."""

    rank: int
    chunk_id: int | None
    chunk_index: int
    page_start: int | None
    page_end: int | None
    page_label: str
    section: str
    preview: str
    exact_phrase: bool
    methods: tuple[str, ...]
    method_label: str
    match_strength: str
    keyword_score: float | None
    semantic_score: float | None
    keyword_rank: int | None
    semantic_rank: int | None
    matched_terms: tuple[str, ...]


@dataclass(frozen=True)
class DocumentSearchResult:
    """Search result for one owned document."""

    document: Any
    query: str
    hits: tuple[DocumentSearchHit, ...]
    mode: str
    exact_result_count: int
    keyword_result_count: int
    semantic_result_count: int
    semantic_fallback: bool
    semantic_error: str | None
    chunks_rebuilt: bool
    embeddings_created: int
    embeddings_reused: int

    @property
    def result_count(self) -> int:
        return len(self.hits)


def search_owned_document(
    *,
    document_id: int,
    user_id: int,
    query: str,
    limit: int = DEFAULT_SEARCH_RESULT_LIMIT,
) -> DocumentSearchResult:
    """
    Search one owned document without generating an AI answer.

    Exact phrase matches are scanned across every current chunk. Hybrid
    BM25 + semantic retrieval supplies concept and keyword matches. The
    two result sets are merged, exact matches are kept first, and the
    returned preview always comes from the original trusted chunk text.
    """

    cleaned_query = _clean_query(query)
    cleaned_limit = _validate_limit(limit)

    try:
        indexed = ensure_owned_document_chunks(
            document_id=document_id,
            user_id=user_id,
        )

    except DocumentChunkNotFoundError as error:
        raise DocumentSearchNotFoundError(str(error)) from error

    except DocumentChunkNotReadyError as error:
        raise DocumentSearchNotReadyError(str(error)) from error

    except DocumentChunkError as error:
        raise DocumentSearchError(
            "LifeOS could not prepare this document for search."
        ) from error

    exact_chunks = _find_exact_phrase_chunks(
        chunks=indexed.chunks,
        query=cleaned_query,
    )

    hybrid_result = None
    hybrid_error: str | None = None

    try:
        hybrid_result = retrieve_owned_document_chunks_hybrid(
            document_id=document_id,
            user_id=user_id,
            query=cleaned_query,
            limit=MAX_SEARCH_RESULT_LIMIT,
        )

    except DocumentHybridRetrievalNotFoundError as error:
        raise DocumentSearchNotFoundError(str(error)) from error

    except DocumentHybridRetrievalNotReadyError as error:
        raise DocumentSearchNotReadyError(str(error)) from error

    except DocumentHybridRetrievalValidationError as error:
        raise DocumentSearchValidationError(str(error)) from error

    except DocumentHybridRetrievalError as error:
        hybrid_error = str(error)

        # Direct exact matches are still useful when semantic/keyword
        # retrieval is temporarily unavailable.
        if not exact_chunks:
            raise DocumentSearchError(str(error)) from error

    hybrid_chunks = (
        list(hybrid_result.chunks or [])
        if hybrid_result is not None
        else []
    )

    hybrid_by_key = {
        _chunk_key(retrieved.chunk): retrieved
        for retrieved in hybrid_chunks
    }

    exact_keys = {
        _chunk_key(chunk)
        for chunk in exact_chunks
    }

    ordered_chunks: list[Any] = []
    seen_keys: set[tuple[int | None, int]] = set()

    # Exact matches that also appear in hybrid retrieval keep hybrid's
    # relevance order instead of falling back to PDF page order.
    for retrieved in hybrid_chunks:
        key = _chunk_key(retrieved.chunk)
        if key not in exact_keys or key in seen_keys:
            continue
        seen_keys.add(key)
        ordered_chunks.append(retrieved.chunk)

    # Include exact phrase matches that were outside the hybrid candidate
    # window so literal search never silently loses a real occurrence.
    for chunk in exact_chunks:
        key = _chunk_key(chunk)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        ordered_chunks.append(chunk)

    # Finally add broader keyword/semantic concept matches.
    for retrieved in hybrid_chunks:
        key = _chunk_key(retrieved.chunk)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        ordered_chunks.append(retrieved.chunk)

    ordered_chunks = ordered_chunks[:cleaned_limit]

    hits: list[DocumentSearchHit] = []

    for rank, chunk in enumerate(ordered_chunks, start=1):
        key = _chunk_key(chunk)
        retrieved = hybrid_by_key.get(key)
        exact_phrase = key in exact_keys

        matched_terms = tuple(
            getattr(retrieved, "matched_terms", ()) or ()
        )

        methods = tuple(
            getattr(retrieved, "retrieval_methods", ()) or ()
        )

        if exact_phrase:
            methods = tuple(dict.fromkeys(("exact",) + methods))

        source_text = _clean_chunk_text(
            getattr(chunk, "text", "")
        )

        if exact_phrase:
            preview = _build_exact_phrase_preview(
                source_text=source_text,
                query=cleaned_query,
                max_characters=SEARCH_PREVIEW_CHARACTERS,
            )
        else:
            preview = build_focused_evidence_preview(
                source_text,
                question=cleaned_query,
                matched_terms=matched_terms,
                max_characters=SEARCH_PREVIEW_CHARACTERS,
            ).text

        keyword_score = getattr(retrieved, "keyword_score", None)
        semantic_score = getattr(retrieved, "semantic_score", None)
        keyword_rank = getattr(retrieved, "keyword_rank", None)
        semantic_rank = getattr(retrieved, "semantic_rank", None)

        hits.append(
            DocumentSearchHit(
                rank=rank,
                chunk_id=getattr(chunk, "id", None),
                chunk_index=int(getattr(chunk, "chunk_index", 0)),
                page_start=getattr(chunk, "page_start", None),
                page_end=getattr(chunk, "page_end", None),
                page_label=_page_label(chunk),
                section=str(
                    getattr(chunk, "section_title", "") or ""
                ).strip(),
                preview=preview,
                exact_phrase=exact_phrase,
                methods=methods,
                method_label=_method_label(methods),
                match_strength=_match_strength(
                    exact_phrase=exact_phrase,
                    methods=methods,
                    matched_terms=matched_terms,
                    semantic_score=semantic_score,
                ),
                keyword_score=(
                    round(float(keyword_score), 4)
                    if keyword_score is not None
                    else None
                ),
                semantic_score=(
                    round(float(semantic_score), 4)
                    if semantic_score is not None
                    else None
                ),
                keyword_rank=keyword_rank,
                semantic_rank=semantic_rank,
                matched_terms=matched_terms,
            )
        )

    if hybrid_result is None:
        mode = "exact_only"
        keyword_count = 0
        semantic_count = 0
        semantic_error = hybrid_error
        chunks_rebuilt = bool(indexed.rebuilt)
        embedded_count = 0
        reused_count = 0
    else:
        mode = hybrid_result.mode
        keyword_count = hybrid_result.keyword_result_count
        semantic_count = hybrid_result.semantic_result_count
        semantic_error = hybrid_result.semantic_error
        chunks_rebuilt = bool(
            indexed.rebuilt or hybrid_result.chunks_rebuilt
        )
        embedded_count = hybrid_result.embedded_count
        reused_count = hybrid_result.reused_count

    return DocumentSearchResult(
        document=indexed.document,
        query=cleaned_query,
        hits=tuple(hits),
        mode=mode,
        exact_result_count=len(exact_chunks),
        keyword_result_count=keyword_count,
        semantic_result_count=semantic_count,
        semantic_fallback=bool(semantic_error),
        semantic_error=semantic_error,
        chunks_rebuilt=chunks_rebuilt,
        embeddings_created=embedded_count,
        embeddings_reused=reused_count,
    )


def _clean_query(query: str) -> str:
    cleaned = " ".join(str(query or "").split()).strip()

    if not cleaned:
        raise DocumentSearchValidationError(
            "Enter a word, phrase, or concept to search for."
        )

    if len(cleaned) > MAX_SEARCH_QUERY_CHARACTERS:
        raise DocumentSearchValidationError(
            "Document search is limited to "
            f"{MAX_SEARCH_QUERY_CHARACTERS:,} characters."
        )

    return cleaned


def _validate_limit(limit: int) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        parsed = DEFAULT_SEARCH_RESULT_LIMIT

    return max(1, min(parsed, MAX_SEARCH_RESULT_LIMIT))


def _find_exact_phrase_chunks(*, chunks: list[Any], query: str) -> list[Any]:
    needle = _normalise_exact_text(query)

    if not needle:
        return []

    matches: list[Any] = []

    for chunk in chunks:
        haystack = _normalise_exact_text(
            _clean_chunk_text(getattr(chunk, "text", ""))
        )

        if needle in haystack:
            matches.append(chunk)

    return matches


def _normalise_exact_text(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def _clean_chunk_text(value: str) -> str:
    return PAGE_MARKER_PATTERN.sub("", str(value or "")).strip()


def _build_exact_phrase_preview(
    *,
    source_text: str,
    query: str,
    max_characters: int,
) -> str:
    """Return a bounded continuous excerpt containing the exact phrase."""

    compact = " ".join(str(source_text or "").split()).strip()

    if not compact:
        return ""

    folded = compact.casefold()
    needle = _normalise_exact_text(query)
    position = folded.find(needle)

    if position < 0:
        return build_focused_evidence_preview(
            compact,
            question=query,
            max_characters=max_characters,
        ).text

    if len(compact) <= max_characters:
        return compact

    before = max_characters // 3
    start = max(0, position - before)
    end = min(len(compact), start + max_characters)

    if end - start < max_characters:
        start = max(0, end - max_characters)

    if start > 0:
        next_space = compact.find(" ", start)
        if 0 <= next_space < end:
            start = next_space + 1

    if end < len(compact):
        previous_space = compact.rfind(" ", start, end)
        if previous_space > start:
            end = previous_space

    excerpt = compact[start:end].strip()
    prefix = "… " if start > 0 else ""
    suffix = " …" if end < len(compact) else ""

    available = max_characters - len(prefix) - len(suffix)
    excerpt = excerpt[:available].rstrip()

    return f"{prefix}{excerpt}{suffix}".strip()


def _chunk_key(chunk: Any) -> tuple[int | None, int]:
    return (
        getattr(chunk, "id", None),
        int(getattr(chunk, "chunk_index", 0)),
    )


def _page_label(chunk: Any) -> str:
    start = getattr(chunk, "page_start", None)
    end = getattr(chunk, "page_end", None)

    if start and end and start != end:
        return f"{start}-{end}"

    if start or end:
        return str(start or end)

    return "Unknown"


def _method_label(methods: tuple[str, ...]) -> str:
    method_set = set(methods)

    if "exact" in method_set:
        if "semantic" in method_set or "keyword" in method_set:
            return "Exact + retrieval"
        return "Exact phrase"

    if {"keyword", "semantic"}.issubset(method_set):
        return "Keyword + semantic"

    if "keyword" in method_set:
        return "Keyword"

    if "semantic" in method_set:
        return "Semantic"

    return "Document match"


def _match_strength(
    *,
    exact_phrase: bool,
    methods: tuple[str, ...],
    matched_terms: tuple[str, ...],
    semantic_score: float | None,
) -> str:
    """Return a display-only match label; it is not an answerability gate."""

    if exact_phrase:
        return "Exact"

    method_set = set(methods)

    if {"keyword", "semantic"}.issubset(method_set):
        return "Strong"

    if len(matched_terms) >= 2:
        return "Strong"

    if semantic_score is not None and float(semantic_score) >= 0.58:
        return "Strong"

    return "Related"

"""Validate user-selected PDF context and resolve it to trusted chunks."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from models import (
    Document,
    DocumentChunk,
    Project,
)


MAX_SELECTED_CONTEXT_CHARACTERS = 5_000
MAX_PREFERRED_SELECTION_CHUNKS = 3

_PAGE_MARKER_RE = re.compile(
    r"^--- Page\s+(\d+)\s+---\s*$",
    flags=re.MULTILINE,
)
_WORD_RE = re.compile(
    r"[\w']+",
    flags=re.UNICODE,
)


class DocumentSelectedContextError(RuntimeError):
    """Base error for selected PDF context."""


class DocumentSelectedContextNotFoundError(
    DocumentSelectedContextError
):
    """Raised when the document is missing or not owned."""


class DocumentSelectedContextValidationError(
    DocumentSelectedContextError
):
    """Raised when selected text is not supported by the PDF."""


@dataclass(frozen=True)
class ValidatedDocumentSelection:
    """One user-selected passage verified against the owned PDF."""

    document: Document
    text: str
    page: int
    section: str

    def as_source(self) -> dict:
        """Return reader-facing saved context metadata."""

        return {
            "context_role": "selected",
            "page": self.page,
            "section": self.section,
            "evidence": self.text,
        }


def validate_owned_pdf_selection(
    *,
    document_id: int,
    user_id: int,
    selected_text: object,
    page: object,
    section: object = "",
) -> ValidatedDocumentSelection:
    """Verify that selected text really exists on the stated PDF page."""

    document = (
        Document.query
        .filter(
            Document.id == int(document_id),
            Document.user_id == int(user_id),
        )
        .first()
    )

    if document is None:
        raise DocumentSelectedContextNotFoundError(
            "The requested document was not found."
        )

    text = _clean_selected_text(
        selected_text
    )

    try:
        page_number = int(
            page
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise DocumentSelectedContextValidationError(
            "The selected PDF page is invalid."
        ) from error

    if page_number <= 0:
        raise DocumentSelectedContextValidationError(
            "The selected PDF page is invalid."
        )

    extracted_text = str(
        document.extracted_text or ""
    )

    if not extracted_text.strip():
        raise DocumentSelectedContextValidationError(
            "This PDF does not have readable text for selected-context questions."
        )

    page_text = _extract_page_text(
        extracted_text,
        page_number,
    )

    if not page_text:
        raise DocumentSelectedContextValidationError(
            "LifeOS could not verify the selected text on that PDF page."
        )

    if not _selection_is_supported(
        selected_text=text,
        page_text=page_text,
    ):
        raise DocumentSelectedContextValidationError(
            "LifeOS could not verify that the selected text belongs to this PDF page."
        )

    return ValidatedDocumentSelection(
        document=document,
        text=text,
        page=page_number,
        section=str(
            section or ""
        ).strip()[:255],
    )


def resolve_selection_chunks(
    selection: ValidatedDocumentSelection,
    *,
    user_id: int,
    limit: int = MAX_PREFERRED_SELECTION_CHUNKS,
) -> list[DocumentChunk]:
    """Resolve a verified visible selection to backend chunks on that page."""

    candidates = (
        DocumentChunk.query
        .filter(
            DocumentChunk.document_id == selection.document.id,
            DocumentChunk.user_id == int(user_id),
            DocumentChunk.page_start <= selection.page,
            DocumentChunk.page_end >= selection.page,
        )
        .order_by(
            DocumentChunk.chunk_index.asc(),
            DocumentChunk.id.asc(),
        )
        .all()
    )

    if not candidates:
        return []

    selection_tokens = _tokens(
        selection.text
    )

    scored: list[
        tuple[float, DocumentChunk]
    ] = []

    for chunk in candidates:
        chunk_text = str(
            chunk.text or ""
        )

        normalized_selection = _normalize_text(
            selection.text
        )
        normalized_chunk = _normalize_text(
            chunk_text
        )

        if normalized_selection in normalized_chunk:
            score = 1.0
        elif normalized_chunk and normalized_chunk in normalized_selection:
            score = min(
                1.0,
                len(normalized_chunk)
                / max(1, len(normalized_selection)),
            )
        else:
            chunk_tokens = _tokens(
                chunk_text
            )
            score = _longest_token_coverage(
                selection_tokens,
                chunk_tokens,
            )

        if score > 0:
            scored.append(
                (
                    score,
                    chunk,
                )
            )

    scored.sort(
        key=lambda item: (
            -item[0],
            item[1].chunk_index,
            item[1].id,
        )
    )

    preferred = [
        chunk
        for score, chunk in scored
        if score >= 0.20
    ][:max(1, min(int(limit), MAX_PREFERRED_SELECTION_CHUNKS))]

    if preferred:
        return preferred

    return [
        scored[0][1]
    ] if scored else []


def _clean_selected_text(
    value: object,
) -> str:
    text = " ".join(
        str(value or "").split()
    ).strip()

    if not text:
        raise DocumentSelectedContextValidationError(
            "Select text from the PDF before asking about it."
        )

    if len(text) > MAX_SELECTED_CONTEXT_CHARACTERS:
        raise DocumentSelectedContextValidationError(
            "The selected passage is too long. Select a smaller part of the PDF."
        )

    return text


def _extract_page_text(
    extracted_text: str,
    page: int,
) -> str:
    matches = list(
        _PAGE_MARKER_RE.finditer(
            extracted_text
        )
    )

    if not matches:
        return extracted_text if page == 1 else ""

    for index, match in enumerate(matches):
        if int(match.group(1)) != page:
            continue

        start = match.end()
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(extracted_text)
        )

        return extracted_text[
            start:end
        ].strip()

    return ""


def _selection_is_supported(
    *,
    selected_text: str,
    page_text: str,
) -> bool:
    selected = _normalize_text(
        selected_text
    )
    page = _normalize_text(
        page_text
    )

    if selected and selected in page:
        return True

    selected_tokens = _tokens(
        selected_text
    )
    page_tokens = _tokens(
        page_text
    )

    if not selected_tokens or not page_tokens:
        return False

    coverage = _longest_token_coverage(
        selected_tokens,
        page_tokens,
    )

    if len(selected_tokens) <= 6:
        return coverage >= 1.0

    return coverage >= 0.80


def _normalize_text(
    value: object,
) -> str:
    text = unicodedata.normalize(
        "NFKC",
        str(value or ""),
    )
    text = text.replace(
        "\u00ad",
        "",
    )
    text = re.sub(
        r"\s+",
        " ",
        text,
    )
    return text.strip().casefold()


def _tokens(
    value: object,
) -> list[str]:
    return [
        token.casefold()
        for token in _WORD_RE.findall(
            unicodedata.normalize(
                "NFKC",
                str(value or ""),
            )
        )
    ]


def _longest_token_coverage(
    selected_tokens: list[str],
    candidate_tokens: list[str],
) -> float:
    if not selected_tokens or not candidate_tokens:
        return 0.0

    match = SequenceMatcher(
        None,
        selected_tokens,
        candidate_tokens,
        autojunk=False,
    ).find_longest_match(
        0,
        len(selected_tokens),
        0,
        len(candidate_tokens),
    )

    return match.size / len(selected_tokens)

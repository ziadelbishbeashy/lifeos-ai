"""Developer-facing OCR diagnostics built from the exact text RAG consumes."""

from __future__ import annotations

import json
from dataclasses import dataclass

from models import Document
from ocr.quality import classify_ocr_quality
from services.document_access_service import DocumentNotFoundError, require_owned_document
from services.document_chunk_service import parse_page_blocks


class DocumentOCRDiagnosticsError(RuntimeError):
    """Base OCR diagnostics error."""


class DocumentOCRDiagnosticsNotFoundError(DocumentOCRDiagnosticsError):
    """Raised when the requested document is missing or not owned."""


@dataclass(frozen=True)
class OCRDiagnosticPage:
    page_number: int
    source: str
    character_count: int
    word_count: int
    confidence: float | None
    quality: str
    selected_provider: str | None
    selected_strategy: str | None
    selection_attempts: tuple[dict, ...]
    text_preview: str
    matched_terms: tuple[str, ...]


@dataclass(frozen=True)
class OCRDiagnostics:
    document_id: int
    status: str
    provider: str | None
    preprocessing_mode: str | None
    total_characters: int
    total_words: int
    average_confidence: float | None
    quality: str | None
    terms: tuple[str, ...]
    pages: tuple[OCRDiagnosticPage, ...]


def build_owned_document_ocr_diagnostics(
    *,
    document_id: int,
    user_id: int,
    terms: tuple[str, ...] = (),
    preview_chars: int = 320,
) -> OCRDiagnostics:
    """Describe the OCR/RAG handoff using ``document.extracted_text``.

    ``parse_page_blocks`` is deliberately reused here so the diagnostic sees
    the same page-marked text that document chunking/RAG sees.
    """

    try:
        document = require_owned_document(document_id=document_id, owner_id=user_id)
    except DocumentNotFoundError as error:
        raise DocumentOCRDiagnosticsNotFoundError(
            "The requested document was not found."
        ) from error

    cleaned_terms = tuple(
        dict.fromkeys(
            term.strip()
            for term in terms
            if str(term or "").strip()
        )
    )

    layout_pages, preprocessing_mode = _read_layout(document)
    page_blocks = parse_page_blocks(str(document.extracted_text or ""))

    pages: list[OCRDiagnosticPage] = []
    for block in page_blocks:
        page_text = str(block.text or "").strip()
        character_count = len(page_text)
        word_count = _count_words(page_text)
        layout = layout_pages.get(str(block.page_number), {})
        confidence = _safe_confidence(layout.get("confidence"))
        source = str(layout.get("source") or "native")
        quality = str(layout.get("quality") or "").strip() or classify_ocr_quality(
            character_count=character_count,
            word_count=word_count,
            average_confidence=confidence if source == "ocr" else None,
        )
        lowered = page_text.casefold()
        matched_terms = tuple(
            term for term in cleaned_terms if term.casefold() in lowered
        )
        preview = " ".join(page_text.split())[: max(40, int(preview_chars))]

        pages.append(
            OCRDiagnosticPage(
                page_number=block.page_number,
                source=source,
                character_count=character_count,
                word_count=word_count,
                confidence=confidence,
                quality=quality,
                selected_provider=(str(layout.get("selected_provider") or "").strip() or None),
                selected_strategy=(str(layout.get("selected_strategy") or "").strip() or None),
                selection_attempts=tuple(
                    item for item in (layout.get("selection_attempts") or []) if isinstance(item, dict)
                ),
                text_preview=preview,
                matched_terms=matched_terms,
            )
        )

    confidence = getattr(document, "ocr_average_confidence", None)
    return OCRDiagnostics(
        document_id=document.id,
        status=str(getattr(document, "ocr_status", "not_needed") or "not_needed"),
        provider=(str(getattr(document, "ocr_provider", "") or "").strip() or None),
        preprocessing_mode=preprocessing_mode,
        total_characters=int(getattr(document, "ocr_total_characters", 0) or 0),
        total_words=int(getattr(document, "ocr_total_words", 0) or 0),
        average_confidence=(float(confidence) if confidence is not None else None),
        quality=(str(getattr(document, "ocr_quality", "") or "").strip() or None),
        terms=cleaned_terms,
        pages=tuple(pages),
    )


def _read_layout(document: Document) -> tuple[dict[str, dict], str | None]:
    raw = str(getattr(document, "ocr_layout_json", "") or "").strip()
    if not raw:
        return {}, None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}, None
    if not isinstance(payload, dict):
        return {}, None
    pages = payload.get("pages")
    metadata = payload.get("metadata")
    if not isinstance(pages, dict):
        pages = {}
    preprocessing_mode = None
    if isinstance(metadata, dict):
        value = str(metadata.get("preprocessing_mode") or "").strip()
        preprocessing_mode = value or None
    return pages, preprocessing_mode


def _count_words(text: str) -> int:
    return len([part for part in str(text or "").split() if part.strip()])


def _safe_confidence(value) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None

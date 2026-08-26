"""Page-aware OCR extraction for Document Brain.

This service repairs only pages whose embedded PDF text is missing or too weak.
Normal text pages keep their native text so OCR remains a fallback rather than a
replacement extraction pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Callable

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ocr.base import OCRError, OCRProvider, OCRWord
from ocr.rendering import OCRRenderError, render_pdf_page_png
from services.pdf_service import (
    MAX_EXTRACTED_TEXT_CHARACTERS,
    clean_extracted_text,
    is_useful_native_page_text,
)
from storage.base import StorageError, StorageService
from storage.service import get_storage


LOW_CONFIDENCE_THRESHOLD = 0.70


class DocumentOCRError(RuntimeError):
    """Raised when LifeOS cannot complete OCR extraction safely."""


@dataclass(frozen=True)
class OCRPageExtraction:
    page_number: int
    text: str
    source: str
    confidence: float | None
    words: tuple[OCRWord, ...] = ()


@dataclass(frozen=True)
class OCRDocumentExtraction:
    text: str
    page_count: int
    native_page_count: int
    ocr_page_count: int
    pages_processed: int
    low_confidence_page_count: int
    average_confidence: float | None
    truncated: bool
    pages: tuple[OCRPageExtraction, ...]


def extract_stored_pdf_with_ocr(
    storage_key: str,
    *,
    provider: OCRProvider,
    storage: StorageService | None = None,
    render_page: Callable[..., bytes] = render_pdf_page_png,
    render_dpi: int = 300,
    max_chars: int = MAX_EXTRACTED_TEXT_CHARACTERS,
    low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
    preprocess_image: Callable[[bytes], bytes] | None = None,
) -> OCRDocumentExtraction:
    """Extract a stored PDF with page-by-page OCR fallback."""

    cleaned_key = str(storage_key or "").strip()
    if not cleaned_key:
        raise DocumentOCRError("A stored PDF is required for OCR.")
    if max_chars <= 0:
        raise ValueError("The extracted-text limit must be positive.")
    if not 0 <= low_confidence_threshold <= 1:
        raise ValueError("OCR confidence threshold must be between 0 and 1.")

    storage_service = storage or get_storage()

    try:
        with storage_service.open(cleaned_key, "rb") as stored_file:
            pdf_bytes = stored_file.read()

        if not pdf_bytes:
            raise DocumentOCRError("The stored PDF is empty.")

        reader = PdfReader(BytesIO(pdf_bytes), strict=False)
        if reader.is_encrypted:
            raise DocumentOCRError(
                "Password-protected PDFs cannot be processed with OCR."
            )

        extracted_pages: list[OCRPageExtraction] = []
        confidence_values: list[float] = []
        low_confidence_page_count = 0
        native_page_count = 0
        ocr_page_count = 0

        for page_number, page in enumerate(reader.pages, start=1):
            try:
                native_text = clean_extracted_text(page.extract_text())
            except Exception:
                # A damaged/missing text layer should trigger OCR for this page
                # rather than abort the complete document.
                native_text = ""

            if is_useful_native_page_text(native_text):
                extracted_pages.append(
                    OCRPageExtraction(
                        page_number=page_number,
                        text=native_text,
                        source="native",
                        confidence=None,
                        words=(),
                    )
                )
                native_page_count += 1
                continue

            try:
                image_bytes = render_page(
                    pdf_bytes,
                    page_index=page_number - 1,
                    dpi=render_dpi,
                )
                ocr_input = (
                    preprocess_image(image_bytes)
                    if preprocess_image is not None
                    else image_bytes
                )
                recognized = provider.recognize_page(
                    ocr_input,
                    page_number=page_number,
                )
            except (OCRError, OCRRenderError) as error:
                raise DocumentOCRError(str(error)) from error
            except Exception as error:
                raise DocumentOCRError(
                    f"LifeOS could not OCR PDF page {page_number}."
                ) from error

            ocr_text = clean_extracted_text(recognized.text)
            # Preserve a tiny native fragment if OCR returns nothing. This is
            # rare, but prevents the repair pass from deleting readable content.
            final_text = ocr_text or native_text

            confidence = recognized.confidence
            if confidence is not None:
                confidence = max(0.0, min(1.0, float(confidence)))
                confidence_values.append(confidence)
                if confidence < low_confidence_threshold:
                    low_confidence_page_count += 1

            extracted_pages.append(
                OCRPageExtraction(
                    page_number=page_number,
                    text=final_text,
                    source="ocr",
                    confidence=confidence,
                    words=tuple(recognized.words or ()),
                )
            )
            ocr_page_count += 1

        text, truncated = _compose_page_marked_text(
            extracted_pages,
            max_chars=max_chars,
        )

        average_confidence = (
            sum(confidence_values) / len(confidence_values)
            if confidence_values
            else None
        )

        return OCRDocumentExtraction(
            text=text,
            page_count=len(reader.pages),
            native_page_count=native_page_count,
            ocr_page_count=ocr_page_count,
            pages_processed=ocr_page_count,
            low_confidence_page_count=low_confidence_page_count,
            average_confidence=average_confidence,
            truncated=truncated,
            pages=tuple(extracted_pages),
        )

    except DocumentOCRError:
        raise
    except (StorageError, PdfReadError, EOFError, OSError, ValueError) as error:
        raise DocumentOCRError(
            "LifeOS could not read this PDF for OCR."
        ) from error


def _compose_page_marked_text(
    pages: list[OCRPageExtraction],
    *,
    max_chars: int,
) -> tuple[str, bool]:
    parts: list[str] = []
    current_length = 0
    truncated = False

    for page in pages:
        page_text = clean_extracted_text(page.text)
        if not page_text:
            continue

        block = f"--- Page {page.page_number} ---\n{page_text}"
        if parts:
            block = "\n\n" + block

        remaining = max_chars - current_length
        if len(block) > remaining:
            if remaining > 0:
                parts.append(block[:remaining].rstrip())
            truncated = True
            break

        parts.append(block)
        current_length += len(block)

    return "".join(parts), truncated

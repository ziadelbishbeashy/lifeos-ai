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

from ocr.base import OCRAttempt, OCRError, OCRProvider, OCRWord
from ocr.rendering import OCRRenderError, render_pdf_page_png
from services.pdf_service import (
    MAX_EXTRACTED_TEXT_CHARACTERS,
    clean_extracted_text,
    is_useful_native_page_text,
)
from storage.base import StorageError, StorageService
from storage.service import get_storage


LOW_CONFIDENCE_THRESHOLD = 0.70

# A page can contain a small amount of *real* native text (a title, a slide
# number, a watermark) while its actual content is a scanned/rendered image
# with no embedded text layer at all. ``is_useful_native_page_text`` alone
# cannot tell these two cases apart, so any page below this character count
# that also carries a large embedded image is treated as "thin text over an
# image" and is still sent through OCR even though it has *some* native text.
THIN_NATIVE_TEXT_CHAR_LIMIT = 300
LARGE_EMBEDDED_IMAGE_MIN_DIMENSION_PX = 600


class DocumentOCRError(RuntimeError):
    """Raised when LifeOS cannot complete OCR extraction safely."""


@dataclass(frozen=True)
class OCRPageExtraction:
    page_number: int
    text: str
    source: str
    confidence: float | None
    words: tuple[OCRWord, ...] = ()
    ocr_reason: str | None = None
    character_count: int = 0
    word_count: int = 0
    provider_name: str | None = None
    provider_strategy: str | None = None
    quality: str | None = None
    attempts: tuple[OCRAttempt, ...] = ()


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
    total_character_count: int = 0
    total_word_count: int = 0


def _count_words(text: str) -> int:
    return len([part for part in str(text or "").split() if part.strip()])


def _page_has_large_embedded_image(
    page,
    *,
    min_dimension_px: int = LARGE_EMBEDDED_IMAGE_MIN_DIMENSION_PX,
) -> bool:
    """Return whether a PDF page carries a large embedded raster image.

    A page that is mostly a scanned/rendered picture (a photographed slide, a
    scanned worksheet) will usually contain at least one embedded image large
    enough to be the page content rather than a small icon or logo. pypdf
    exposes embedded images via ``page.images``; any failure to read them is
    treated as "no image" rather than raised, since this is only an extra
    signal for deciding whether to OCR a page that already has *some* native
    text.
    """

    try:
        images = list(page.images)
    except Exception:
        return False

    for image_file in images:
        try:
            image = image_file.image
            width = int(getattr(image, "width", 0) or 0)
            height = int(getattr(image, "height", 0) or 0)
        except Exception:
            continue
        if width >= min_dimension_px or height >= min_dimension_px:
            return True
    return False


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

            native_text_useful = is_useful_native_page_text(native_text)
            large_embedded_image = _page_has_large_embedded_image(page)
            thin_native_text_over_image = (
                bool(native_text.strip())
                and len(native_text) < THIN_NATIVE_TEXT_CHAR_LIMIT
                and large_embedded_image
            )
            needs_ocr_despite_native_text = (
                native_text_useful and thin_native_text_over_image
            )

            if native_text_useful and not needs_ocr_despite_native_text:
                extracted_pages.append(
                    OCRPageExtraction(
                        page_number=page_number,
                        text=native_text,
                        source="native",
                        confidence=None,
                        words=(),
                        character_count=len(native_text),
                        word_count=_count_words(native_text),
                    )
                )
                native_page_count += 1
                continue

            ocr_reason = (
                "thin_native_text_over_image"
                if thin_native_text_over_image
                else "no_useful_native_text"
            )

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
            # When a page had thin native text over an image, prefer whichever
            # text is actually longer/more useful rather than always trusting
            # the OCR pass, since a bad scan can still OCR to very little.
            if ocr_text and native_text:
                final_text = ocr_text if len(ocr_text) >= len(native_text) else native_text
            else:
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
                    ocr_reason=ocr_reason,
                    character_count=len(final_text),
                    word_count=_count_words(final_text),
                    provider_name=recognized.provider_name or provider.name,
                    provider_strategy=recognized.strategy,
                    quality=recognized.quality,
                    attempts=tuple(recognized.attempts or ()),
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
            total_character_count=sum(page.character_count for page in extracted_pages),
            total_word_count=sum(page.word_count for page in extracted_pages),
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

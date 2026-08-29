"""PDF validation and extraction services for Document Brain."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from storage.base import StorageService ,StorageError
from storage.service import get_storage 

PDF_SIGNATURE = b"%PDF-"


class PDFValidationError(ValueError):
    """Raised when an uploaded file is not a valid supported PDF."""


@dataclass(frozen=True)
class ValidatedPDF:
    """Safe information collected from a validated PDF upload."""

    original_name: str
    safe_name: str
    size_bytes: int

@dataclass(frozen=True)
class StoredPDF:
    """Information about a PDF saved in LifeOS storage."""

    original_name: str
    safe_name: str
    size_bytes: int
    storage_key: str


def validate_pdf_upload(
    upload: FileStorage | None,
    *,
    max_bytes: int,
) -> ValidatedPDF:
    """Validate an uploaded PDF without saving it."""

    if upload is None or not upload.filename:
        raise PDFValidationError(
            "Please select a PDF file."
        )

    original_name = upload.filename.strip()
    safe_name = secure_filename(original_name)

    if not safe_name:
        raise PDFValidationError(
            "The uploaded file has an invalid filename."
        )

    extension = Path(safe_name).suffix.lower()

    if extension != ".pdf":
        raise PDFValidationError(
            "Only PDF files are supported."
        )

    if max_bytes <= 0:
        raise ValueError(
            "The maximum upload size must be positive."
        )

    try:
        upload.stream.seek(0, 2)
        size_bytes = upload.stream.tell()
        upload.stream.seek(0)
    except (AttributeError, OSError) as error:
        raise PDFValidationError(
            "LifeOS could not inspect the uploaded file."
        ) from error

    if size_bytes == 0:
        raise PDFValidationError(
            "The uploaded PDF is empty."
        )

    if size_bytes > max_bytes:
        max_megabytes = max_bytes // (1024 * 1024)

        raise PDFValidationError(
            f"The PDF cannot exceed {max_megabytes} MB."
        )

    signature = upload.stream.read(
        len(PDF_SIGNATURE)
    )
    upload.stream.seek(0)

    if signature != PDF_SIGNATURE:
        raise PDFValidationError(
            "The selected file does not appear to be a valid PDF."
        )

    return ValidatedPDF(
        original_name=original_name,
        safe_name=safe_name,
        size_bytes=size_bytes,
    )

def store_pdf_upload(
    upload: FileStorage | None,
    *,
    owner_id: int,
    project_id: int | None = None,
    max_bytes: int,
    storage: StorageService | None = None,
) -> StoredPDF:
    """Validate and securely store an uploaded LifeOS PDF.

    Project documents keep their existing project namespace. Documents uploaded
    directly into another workspace (for example a Module) use the user's
    general document namespace instead of creating a fake Project.
    """

    if owner_id <= 0:
        raise ValueError(
            "A valid document owner is required."
        )

    if project_id is not None and project_id <= 0:
        raise ValueError(
            "A valid project is required."
        )

    validated = validate_pdf_upload(
        upload,
        max_bytes=max_bytes,
    )

    if upload is None:
        raise PDFValidationError(
            "Please select a PDF file."
        )

    storage_service = storage or get_storage()

    namespace = (
        f"user-{owner_id}-project-{project_id}"
        if project_id is not None
        else f"user-{owner_id}-documents"
    )

    upload.stream.seek(0)

    storage_key = storage_service.save(
        upload.stream,
        original_name=validated.safe_name,
        namespace=namespace,
    )

    upload.stream.seek(0)

    return StoredPDF(
        original_name=validated.original_name,
        safe_name=validated.safe_name,
        size_bytes=validated.size_bytes,
        storage_key=storage_key,
    )


MAX_EXTRACTED_TEXT_CHARACTERS = 200_000
DEFAULT_MAX_PDF_PAGES = 300


class PDFExtractionError(RuntimeError):
    """Raised when text cannot be extracted from a stored PDF."""


class PDFResourceLimitError(PDFExtractionError):
    """Raised when a valid PDF exceeds a reviewed Step 20 processing limit."""


@dataclass(frozen=True)
class ExtractedPDFText:
    """Text and metadata extracted from a PDF."""

    text: str
    page_count: int
    pages_with_text: int
    truncated: bool
    pages_needing_ocr: tuple[int, ...] = ()


def clean_extracted_text(
    value: str | None,
) -> str:
    """Clean PDF text while keeping readable paragraph structure."""

    text = str(value or "").replace("\x00", "")

    text = (
        text
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )

    lines = [
        line.rstrip()
        for line in text.split("\n")
    ]

    cleaned = "\n".join(lines).strip()

    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace(
            "\n\n\n",
            "\n\n",
        )

    return cleaned




def is_useful_native_page_text(
    value: str | None,
) -> bool:
    """Return whether embedded PDF text is reliable enough to avoid OCR.

    Some scanned PDFs contain only a few garbage glyphs or an invisible text
    artifact. LifeOS keeps any native text it can read, but marks suspiciously
    thin pages for OCR so mixed PDFs can be repaired page-by-page.
    """

    text = clean_extracted_text(value)
    if not text:
        return False

    alphanumeric = sum(character.isalnum() for character in text)
    words = [part for part in text.split() if any(ch.isalnum() for ch in part)]

    if alphanumeric >= 12 and len(words) >= 2:
        return True

    if alphanumeric >= 24:
        return True

    return False


def extract_pdf_text(
    storage_key: str,
    *,
    storage: StorageService | None = None,
    max_chars: int = MAX_EXTRACTED_TEXT_CHARACTERS,
    max_pages: int = DEFAULT_MAX_PDF_PAGES,
) -> ExtractedPDFText:
    """Extract readable embedded text from a stored PDF."""

    cleaned_key = str(storage_key or "").strip()

    if not cleaned_key:
        raise PDFExtractionError(
            "A stored PDF is required for text extraction."
        )

    if max_chars <= 0:
        raise ValueError(
            "The extracted-text limit must be positive."
        )

    if max_pages <= 0:
        raise ValueError(
            "The PDF page limit must be positive."
        )

    storage_service = storage or get_storage()

    try:
        with storage_service.open(
            cleaned_key,
            "rb",
        ) as stored_file:
            reader = PdfReader(
                stored_file,
                strict=False,
            )

            if reader.is_encrypted:
                raise PDFExtractionError(
                    "Password-protected PDFs are not supported yet."
                )

            page_count = len(reader.pages)
            if page_count > max_pages:
                raise PDFResourceLimitError(
                    f"This PDF has {page_count} pages. LifeOS can process at most "
                    f"{max_pages} pages per PDF with the current Step 20 limits."
                )

            pages_with_text = 0
            pages_needing_ocr: list[int] = []
            text_parts: list[str] = []
            current_length = 0
            truncated = False

            for page_number, page in enumerate(
                reader.pages,
                start=1,
            ):
                page_text = clean_extracted_text(
                    page.extract_text()
                )

                if not page_text:
                    pages_needing_ocr.append(page_number)
                    continue

                pages_with_text += 1

                if not is_useful_native_page_text(page_text):
                    pages_needing_ocr.append(page_number)

                page_block = (
                    f"--- Page {page_number} ---\n"
                    f"{page_text}"
                )

                if text_parts:
                    page_block = "\n\n" + page_block

                # Keep inspecting later pages even after the text payload reaches
                # its cap. OCR readiness must describe the complete PDF, not only
                # the prefix retained for RAG storage.
                if truncated:
                    continue

                remaining = max_chars - current_length

                if len(page_block) > remaining:
                    if remaining > 0:
                        text_parts.append(
                            page_block[:remaining].rstrip()
                        )
                        current_length += remaining

                    truncated = True
                    continue

                text_parts.append(page_block)
                current_length += len(page_block)

            return ExtractedPDFText(
                text="".join(text_parts),
                page_count=page_count,
                pages_with_text=pages_with_text,
                truncated=truncated,
                pages_needing_ocr=tuple(pages_needing_ocr),
            )

    except PDFExtractionError:
        raise

    except (
        StorageError,
        PdfReadError,
        EOFError,
        OSError,
        ValueError,
    ) as error:
        raise PDFExtractionError(
            "LifeOS could not extract text from this PDF."
        ) from error
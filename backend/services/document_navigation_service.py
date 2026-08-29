"""Ownership-safe navigation helpers for Document Brain sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from models import (
    Document,
    DocumentChunk,
    Project,
)
from storage.base import StorageError
from storage.service import get_storage


class DocumentNavigationError(RuntimeError):
    """Base error for Document Brain navigation."""


class DocumentNavigationNotFoundError(
    DocumentNavigationError
):
    """Raised when a document or source chunk is missing or not owned."""


class DocumentNavigationNotReadyError(
    DocumentNavigationError
):
    """Raised when a stored PDF is not currently available."""


class DocumentNavigationValidationError(
    DocumentNavigationError
):
    """Raised when navigation input is invalid."""


@dataclass(frozen=True)
class DocumentNavigationPassage:
    """One trusted document chunk prepared for navigation UI."""

    chunk_id: int
    chunk_index: int
    page_start: int | None
    page_end: int | None
    page_label: str
    section: str
    text: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "page_label": self.page_label,
            "section": self.section,
            "text": self.text,
        }


@dataclass(frozen=True)
class DocumentContextResult:
    """Previous/current/next source context for one owned document."""

    document: Document
    previous: DocumentNavigationPassage | None
    current: DocumentNavigationPassage
    next: DocumentNavigationPassage | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document.id,
            "previous": (
                self.previous.as_dict()
                if self.previous is not None
                else None
            ),
            "current": self.current.as_dict(),
            "next": (
                self.next.as_dict()
                if self.next is not None
                else None
            ),
        }


@dataclass(frozen=True)
class OwnedDocumentFile:
    """Validated stored PDF metadata for an owned document."""

    document: Document
    filename: str
    storage_key: str
    local_path: Path | None


def get_owned_document_context(
    *,
    document_id: int,
    user_id: int,
    chunk_id: int,
) -> DocumentContextResult:
    """
    Return previous/current/next trusted chunks.

    Neighbouring chunks are allowed to cross page boundaries. The frontend
    receives each passage's own page label so page transitions can be shown
    explicitly in the context drawer.
    """

    cleaned_document_id = _positive_int(
        document_id,
        field_name="document id",
    )
    cleaned_user_id = _positive_int(
        user_id,
        field_name="user id",
    )
    cleaned_chunk_id = _positive_int(
        chunk_id,
        field_name="chunk id",
    )

    document = _find_owned_document(
        document_id=cleaned_document_id,
        user_id=cleaned_user_id,
    )

    if document is None:
        raise DocumentNavigationNotFoundError(
            "The requested document was not found."
        )

    current_chunk = (
        DocumentChunk.query
        .filter(
            DocumentChunk.id == cleaned_chunk_id,
            DocumentChunk.document_id == document.id,
            DocumentChunk.user_id == cleaned_user_id,
        )
        .first()
    )

    if current_chunk is None:
        raise DocumentNavigationNotFoundError(
            "The requested document passage was not found."
        )

    previous_chunk = (
        DocumentChunk.query
        .filter(
            DocumentChunk.document_id == document.id,
            DocumentChunk.user_id == cleaned_user_id,
            DocumentChunk.chunk_index < current_chunk.chunk_index,
        )
        .order_by(
            DocumentChunk.chunk_index.desc(),
            DocumentChunk.id.desc(),
        )
        .first()
    )

    next_chunk = (
        DocumentChunk.query
        .filter(
            DocumentChunk.document_id == document.id,
            DocumentChunk.user_id == cleaned_user_id,
            DocumentChunk.chunk_index > current_chunk.chunk_index,
        )
        .order_by(
            DocumentChunk.chunk_index.asc(),
            DocumentChunk.id.asc(),
        )
        .first()
    )

    return DocumentContextResult(
        document=document,
        previous=_passage_from_chunk(
            previous_chunk
        ),
        current=_passage_from_chunk(
            current_chunk
        ),
        next=_passage_from_chunk(
            next_chunk
        ),
    )


def prepare_owned_document_file(
    *,
    document_id: int,
    user_id: int,
) -> OwnedDocumentFile:
    """
    Validate ownership and resolve the stored PDF without exposing raw paths.

    Local development returns a local path so Flask can support efficient
    range/conditional requests. A future cloud backend can keep local_path
    as None and stream through the same protected route.
    """

    cleaned_document_id = _positive_int(
        document_id,
        field_name="document id",
    )
    cleaned_user_id = _positive_int(
        user_id,
        field_name="user id",
    )

    document = _find_owned_document(
        document_id=cleaned_document_id,
        user_id=cleaned_user_id,
    )

    if document is None:
        raise DocumentNavigationNotFoundError(
            "The requested document was not found."
        )

    storage_key = str(
        document.file_path or ""
    ).strip()

    if not storage_key:
        raise DocumentNavigationNotReadyError(
            "The original PDF is not available."
        )

    try:
        storage = get_storage()

        if not storage.exists(
            storage_key
        ):
            raise DocumentNavigationNotReadyError(
                "The original PDF is not available."
            )

        local_path = storage.path_for(
            storage_key
        )

    except DocumentNavigationNotReadyError:
        raise

    except StorageError as error:
        raise DocumentNavigationError(
            "LifeOS could not access the stored PDF."
        ) from error

    return OwnedDocumentFile(
        document=document,
        filename=_safe_pdf_name(
            document.filename
        ),
        storage_key=storage_key,
        local_path=local_path,
    )


def _find_owned_document(
    *,
    document_id: int,
    user_id: int,
) -> Document | None:
    """Resolve ownership through the document's project."""

    return (
        Document.query
        .filter(
            Document.id == document_id,
            Document.user_id == user_id,
        )
        .first()
    )


def _passage_from_chunk(
    chunk: DocumentChunk | None,
) -> DocumentNavigationPassage | None:
    if chunk is None:
        return None

    return DocumentNavigationPassage(
        chunk_id=int(
            chunk.id
        ),
        chunk_index=int(
            chunk.chunk_index
        ),
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        page_label=_page_label(
            chunk
        ),
        section=str(
            chunk.section_title or ""
        ).strip(),
        text=str(
            chunk.text or ""
        ).strip(),
    )


def _page_label(
    chunk: DocumentChunk,
) -> str:
    start = chunk.page_start
    end = chunk.page_end

    if (
        start is not None
        and end is not None
        and start != end
    ):
        return f"{start}-{end}"

    page = (
        start
        if start is not None
        else end
    )

    return (
        str(page)
        if page is not None
        else "Unknown"
    )


def _safe_pdf_name(
    value: object,
) -> str:
    filename = str(
        value or "document.pdf"
    ).strip()

    if not filename:
        filename = "document.pdf"

    if not filename.casefold().endswith(
        ".pdf"
    ):
        filename = f"{filename}.pdf"

    return filename[:255]


def _positive_int(
    value: object,
    *,
    field_name: str,
) -> int:
    try:
        parsed = int(
            value
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise DocumentNavigationValidationError(
            f"The {field_name} is invalid."
        ) from error

    if parsed <= 0:
        raise DocumentNavigationValidationError(
            f"The {field_name} is invalid."
        )

    return parsed

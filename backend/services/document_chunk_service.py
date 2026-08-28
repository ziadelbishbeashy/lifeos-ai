"""Page-aware chunk creation for Document Brain retrieval."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import (
    Document,
    DocumentChunk,
    DocumentTable,
    Project,
)


DEFAULT_MAX_CHARS = 1_800
DEFAULT_OVERLAP_CHARS = 250
MIN_SPLIT_POSITION_RATIO = 0.6

PAGE_MARKER_PATTERN = re.compile(
    r"^--- Page\s+(\d+)\s+---\s*$",
    flags=re.MULTILINE,
)


class DocumentChunkError(RuntimeError):
    """Raised when document chunks cannot be created."""


class DocumentChunkNotFoundError(DocumentChunkError):
    """Raised when a document is missing or not owned."""


class DocumentChunkNotReadyError(DocumentChunkError):
    """Raised when the document has no readable text."""


@dataclass(frozen=True)
class PageBlock:
    """Extracted text belonging to one PDF page."""

    page_number: int
    text: str


@dataclass(frozen=True)
class BuiltChunk:
    """A chunk prepared before database persistence."""

    chunk_index: int
    page_start: int
    page_end: int
    section_title: str | None
    text: str
    character_count: int
    content_type: str = "text"
    table_id: int | None = None


@dataclass(frozen=True)
class RebuiltDocumentChunks:
    """Result returned after rebuilding stored chunks."""

    document: Document
    chunks: list[DocumentChunk]
    source_fingerprint: str

@dataclass(frozen=True)
class EnsuredDocumentChunks:
    """Current searchable chunks for one document."""

    document: Document
    chunks: list[DocumentChunk]
    source_fingerprint: str
    rebuilt: bool

def parse_page_blocks(
    extracted_text: str,
) -> list[PageBlock]:
    """Split extracted text using LifeOS PDF page markers."""

    cleaned_text = str(
        extracted_text or ""
    ).replace("\r\n", "\n").replace("\r", "\n").strip()

    if not cleaned_text:
        return []

    matches = list(
        PAGE_MARKER_PATTERN.finditer(cleaned_text)
    )

    if not matches:
        return [
            PageBlock(
                page_number=1,
                text=cleaned_text,
            )
        ]

    pages: list[PageBlock] = []

    for index, match in enumerate(matches):
        page_number = int(
            match.group(1)
        )

        content_start = match.end()

        content_end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(cleaned_text)
        )

        page_text = cleaned_text[
            content_start:content_end
        ].strip()

        if not page_text:
            continue

        pages.append(
            PageBlock(
                page_number=page_number,
                text=page_text,
            )
        )

    return pages


def build_document_chunks(
    extracted_text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[BuiltChunk]:
    """Build deterministic overlapping chunks from page-based text."""

    _validate_chunk_limits(
        max_chars=max_chars,
        overlap_chars=overlap_chars,
    )

    pages = parse_page_blocks(
        extracted_text
    )

    chunks: list[BuiltChunk] = []
    chunk_index = 0

    for page in pages:
        page_parts = _split_text_with_overlap(
            page.text,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )

        section_title = _detect_section_title(
            page.text
        )

        for part in page_parts:
            chunk_text = (
                f"--- Page {page.page_number} ---\n"
                f"{part}"
            )

            chunks.append(
                BuiltChunk(
                    chunk_index=chunk_index,
                    page_start=page.page_number,
                    page_end=page.page_number,
                    section_title=section_title,
                    text=chunk_text,
                    character_count=len(chunk_text),
                )
            )

            chunk_index += 1

    return chunks


def rebuild_owned_document_chunks(
    *,
    document_id: int,
    user_id: int,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> RebuiltDocumentChunks:
    """Replace stored chunks for an owned readable document."""

    document = _find_owned_document(
        document_id=document_id,
        user_id=user_id,
    )

    if document is None:
        raise DocumentChunkNotFoundError(
            "The requested document was not found."
        )

    extracted_text = str(
        document.extracted_text or ""
    ).strip()

    if not extracted_text:
        raise DocumentChunkNotReadyError(
            "This document has no readable extracted text."
        )

    built_chunks = build_document_chunks(
        extracted_text,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
    )
    document_tables = _document_tables(document_id=document.id, user_id=user_id)
    next_index = len(built_chunks)
    for table in document_tables:
        table_text = str(table.markdown_text or "").strip()
        if not table_text:
            continue
        chunk_text = f"--- Page {table.page_number} ---\n[STRUCTURED TABLE {table.table_index}]\n{table_text}"
        built_chunks.append(BuiltChunk(
            chunk_index=next_index, page_start=table.page_number, page_end=table.page_number,
            section_title=table.title or f"Table {table.table_index}", text=chunk_text,
            character_count=len(chunk_text), content_type="table", table_id=table.id,
        ))
        next_index += 1
    if not built_chunks:
        raise DocumentChunkNotReadyError("No searchable chunks could be created.")
    fingerprint = create_index_fingerprint(extracted_text=extracted_text, tables=document_tables)
    stored_chunks = [
        DocumentChunk(
            document_id=document.id, user_id=user_id, chunk_index=chunk.chunk_index,
            page_start=chunk.page_start, page_end=chunk.page_end, section_title=chunk.section_title,
            content_type=chunk.content_type, table_id=chunk.table_id, text=chunk.text,
            character_count=chunk.character_count, source_fingerprint=fingerprint,
        ) for chunk in built_chunks
    ]

    try:
        
        existing_chunks = (
            DocumentChunk.query
            .filter_by(
                document_id=document.id,
                user_id=user_id,
            )
            .all()
        )

        for existing_chunk in existing_chunks:
            db.session.delete(existing_chunk)

        # Complete deletion before inserting replacement chunks.
        db.session.flush()

        db.session.add_all(
            stored_chunks
        )

        db.session.commit()

    except SQLAlchemyError as error:
        db.session.rollback()

        raise DocumentChunkError(
            "LifeOS could not save the document chunks."
        ) from error

    return RebuiltDocumentChunks(
        document=document,
        chunks=stored_chunks,
        source_fingerprint=fingerprint,
    )

def ensure_owned_document_chunks(
    *,
    document_id: int,
    user_id: int,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> EnsuredDocumentChunks:
    """
    Return current document chunks.

    Existing chunks are reused when they match the current
    extracted text. Stale or incomplete chunks are rebuilt.
    """

    document = _find_owned_document(
        document_id=document_id,
        user_id=user_id,
    )

    if document is None:
        raise DocumentChunkNotFoundError(
            "The requested document was not found."
        )

    extracted_text = str(
        document.extracted_text or ""
    ).strip()

    if not extracted_text:
        raise DocumentChunkNotReadyError(
            "This document has no readable extracted text."
        )

    current_fingerprint = create_index_fingerprint(
        extracted_text=extracted_text,
        tables=_document_tables(document_id=document.id, user_id=user_id),
    )

    existing_chunks = (
        DocumentChunk.query
        .filter_by(
            document_id=document.id,
            user_id=user_id,
        )
        .order_by(
            DocumentChunk.chunk_index.asc()
        )
        .all()
    )

    expected_indexes = list(
        range(len(existing_chunks))
    )

    existing_indexes = [
        chunk.chunk_index
        for chunk in existing_chunks
    ]

    chunks_are_current = (
        bool(existing_chunks)
        and existing_indexes == expected_indexes
        and all(
            chunk.source_fingerprint
            == current_fingerprint
            for chunk in existing_chunks
        )
        and all(
            bool(str(chunk.text or "").strip())
            for chunk in existing_chunks
        )
    )

    if chunks_are_current:
        return EnsuredDocumentChunks(
            document=document,
            chunks=existing_chunks,
            source_fingerprint=current_fingerprint,
            rebuilt=False,
        )

    rebuilt = rebuild_owned_document_chunks(
        document_id=document.id,
        user_id=user_id,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
    )

    return EnsuredDocumentChunks(
        document=rebuilt.document,
        chunks=rebuilt.chunks,
        source_fingerprint=rebuilt.source_fingerprint,
        rebuilt=True,
    )  



def create_source_fingerprint(
    extracted_text: str,
) -> str:
    """Create a fingerprint for the current extracted document text."""

    return hashlib.sha256(
        str(extracted_text or "").encode("utf-8")
    ).hexdigest()


def create_index_fingerprint(*, extracted_text: str, tables: list[DocumentTable]) -> str:
    base = create_source_fingerprint(extracted_text)
    if not tables:
        return base
    parts = [base]
    for table in tables:
        table_hash = hashlib.sha256(str(table.markdown_text or "").encode("utf-8")).hexdigest()
        parts.append(f"table:{table.page_number}:{table.table_index}:{table.source_fingerprint}:{table_hash}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _document_tables(*, document_id: int, user_id: int) -> list[DocumentTable]:
    return (DocumentTable.query.filter_by(document_id=document_id, user_id=user_id)
            .order_by(DocumentTable.page_number.asc(), DocumentTable.table_index.asc()).all())


def _find_owned_document(
    *,
    document_id: int,
    user_id: int,
) -> Document | None:
    """Return a document only when its project belongs to the user."""

    return (
        Document.query
        .join(
            Project,
            Document.project_id == Project.id,
        )
        .filter(
            Document.id == document_id,
            Project.user_id == user_id,
        )
        .first()
    )


def _split_text_with_overlap(
    text: str,
    *,
    max_chars: int,
    overlap_chars: int,
) -> list[str]:
    """Split text near whitespace while preserving overlap."""

    cleaned = "\n".join(
        line.rstrip()
        for line in str(text or "").splitlines()
    ).strip()

    if not cleaned:
        return []

    if len(cleaned) <= max_chars:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    text_length = len(cleaned)

    while start < text_length:
        proposed_end = min(
            start + max_chars,
            text_length,
        )

        end = proposed_end

        if proposed_end < text_length:
            minimum_split = (
                start
                + int(
                    max_chars
                    * MIN_SPLIT_POSITION_RATIO
                )
            )

            whitespace_position = cleaned.rfind(
                " ",
                minimum_split,
                proposed_end,
            )

            newline_position = cleaned.rfind(
                "\n",
                minimum_split,
                proposed_end,
            )

            best_split = max(
                whitespace_position,
                newline_position,
            )

            if best_split > start:
                end = best_split

        chunk = cleaned[
            start:end
        ].strip()

        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        next_start = max(
            end - overlap_chars,
            start + 1,
        )

        start = next_start

    return chunks


def _detect_section_title(
    page_text: str,
) -> str | None:
    """Use a short first line as a possible section heading."""

    lines = [
        line.strip()
        for line in str(page_text or "").splitlines()
        if line.strip()
    ]

    if not lines:
        return None

    candidate = lines[0]

    if len(candidate) > 120:
        return None

    if candidate.endswith(
        (
            ".",
            "?",
            "!",
            ";",
        )
    ):
        return None

    return candidate[:255]


def _validate_chunk_limits(
    *,
    max_chars: int,
    overlap_chars: int,
) -> None:
    if max_chars < 300:
        raise ValueError(
            "Chunk size must be at least 300 characters."
        )

    if overlap_chars < 0:
        raise ValueError(
            "Chunk overlap cannot be negative."
        )

    if overlap_chars >= max_chars:
        raise ValueError(
            "Chunk overlap must be smaller than chunk size."
        )
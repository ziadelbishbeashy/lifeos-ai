"""Step 14 — immutable document version history and stale-result control.

A document version is never overwritten. A new PDF becomes a new ``Document``
row inside one ``DocumentVersionFamily``. Exactly one family member is treated
as current by the application; previous versions remain readable and comparable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
from pathlib import PurePath
from typing import Any

from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.datastructures import FileStorage

from database import db
from models import (
    Document,
    DocumentCollectionItem,
    DocumentAIAnalysis,
    DocumentQuestion,
    DocumentTaskSuggestion,
    DocumentVersionFamily,
    Project,
    ProjectQuestion,
)
from services.document_access_service import (
    DocumentNotFoundError,
    require_owned_document,
)
from services.document_embedding_service import (
    DocumentEmbeddingError,
    ensure_owned_document_embeddings,
)
from services.document_service import (
    CreatedProjectDocument,
    DocumentUploadError,
    create_project_pdf_document,
)
from storage.base import StorageError, StorageService
from storage.service import get_storage


VERSIONING_SCHEMA_VERSION = "document-versioning-v1"
PAGE_MARKER_PATTERN = re.compile(
    r"--- Page\s+(\d+)\s+---",
    flags=re.IGNORECASE,
)


class DocumentVersionError(RuntimeError):
    """Base error for Step 14 document versioning."""


class DocumentVersionValidationError(DocumentVersionError, ValueError):
    """Raised when a requested version operation is invalid."""


class DocumentVersionNotFoundError(DocumentVersionError, LookupError):
    """Raised when a version family/document is missing or not owned."""


class DocumentVersionPersistenceError(DocumentVersionError):
    """Raised when a version relationship cannot be saved safely."""


@dataclass(frozen=True)
class DocumentVersionHistory:
    document: Document
    family: DocumentVersionFamily | None
    versions: list[Document]
    current_document: Document


@dataclass(frozen=True)
class CreatedDocumentVersion:
    upload_result: CreatedProjectDocument
    family: DocumentVersionFamily
    previous_document: Document
    current_document: Document
    change_summary: dict[str, Any]
    outdated_analyses: int
    outdated_questions: int
    outdated_suggestions: int
    outdated_project_questions: int
    embeddings_succeeded: bool
    embedding_message: str | None



def current_document_filter():
    """SQL expression selecting standalone/current version records only."""

    return or_(
        Document.version_family_id.is_(None),
        # SQL Server BIT columns must be compared with = 1.  Using
        # ``.is_(True)`` compiles to ``IS 1`` under the MSSQL dialect,
        # which SQL Server rejects with "Incorrect syntax near '1'".
        Document.is_current_version == True,  # noqa: E712
    )



def get_owned_document_version_history(
    *,
    document_id: int,
    owner_id: int,
) -> DocumentVersionHistory:
    """Return ordered version history without exposing another user's family."""

    try:
        document = require_owned_document(
            document_id=document_id,
            owner_id=owner_id,
        )
    except DocumentNotFoundError as error:
        raise DocumentVersionNotFoundError(
            "The requested document was not found."
        ) from error

    if document.version_family_id is None:
        return DocumentVersionHistory(
            document=document,
            family=None,
            versions=[document],
            current_document=document,
        )

    family = (
        DocumentVersionFamily.query
        .join(
            Project,
            DocumentVersionFamily.project_id == Project.id,
        )
        .filter(
            DocumentVersionFamily.id == document.version_family_id,
            DocumentVersionFamily.user_id == owner_id,
            Project.user_id == owner_id,
        )
        .first()
    )

    if family is None:
        raise DocumentVersionNotFoundError(
            "The requested document version history was not found."
        )

    versions = (
        Document.query
        .filter_by(
            version_family_id=family.id,
            project_id=family.project_id,
        )
        .order_by(
            Document.version_number.asc(),
            Document.uploaded_at.asc(),
            Document.id.asc(),
        )
        .all()
    )

    current_document = next(
        (
            item
            for item in reversed(versions)
            if item.is_current_version
        ),
        None,
    )

    if current_document is None and versions:
        current_document = versions[-1]

    if current_document is None:
        raise DocumentVersionNotFoundError(
            "This version history does not contain a document."
        )

    return DocumentVersionHistory(
        document=document,
        family=family,
        versions=versions,
        current_document=current_document,
    )



def create_new_document_version(
    upload: FileStorage | None,
    *,
    source_document_id: int,
    owner_id: int,
    max_bytes: int,
    storage: StorageService | None = None,
) -> CreatedDocumentVersion:
    """Upload and activate a new immutable version of one owned document."""

    storage_service = storage or get_storage()

    try:
        source_document = require_owned_document(
            document_id=source_document_id,
            owner_id=owner_id,
        )
    except DocumentNotFoundError as error:
        raise DocumentVersionNotFoundError(
            "The source document was not found."
        ) from error

    if source_document.project_id is None:
        raise DocumentVersionValidationError(
            "Only project documents can have version history."
        )

    history = get_owned_document_version_history(
        document_id=source_document.id,
        owner_id=owner_id,
    )

    previous_document = history.current_document

    # Reuse the tested upload/extraction/chunking workflow. The new file is a
    # separate immutable Document row; the version relationship is attached
    # only after the PDF itself has been stored safely.
    upload_result = create_project_pdf_document(
        upload,
        owner_id=owner_id,
        project_id=source_document.project_id,
        max_bytes=max_bytes,
        storage=storage_service,
    )

    new_document = upload_result.document

    old_file_fingerprint = _storage_fingerprint(
        storage_service,
        previous_document.file_path,
    )
    new_file_fingerprint = _storage_fingerprint(
        storage_service,
        new_document.file_path,
    )

    same_extracted_text = (
        _text_fingerprint(
            str(previous_document.extracted_text or "")
        )
        == _text_fingerprint(
            str(new_document.extracted_text or "")
        )
    )
    same_file = (
        bool(old_file_fingerprint)
        and bool(new_file_fingerprint)
        and old_file_fingerprint == new_file_fingerprint
    )

    if same_extracted_text and same_file:
        _cleanup_unlinked_upload(
            document_id=new_document.id,
            storage_key=upload_result.storage_key,
            storage=storage_service,
        )
        raise DocumentVersionValidationError(
            "The selected PDF is identical to the current version."
        )

    try:
        family = history.family

        if family is None:
            family = DocumentVersionFamily(
                project_id=source_document.project_id,
                user_id=owner_id,
                name=_family_name(
                    source_document.filename
                ),
            )
            db.session.add(family)
            db.session.flush()

            source_document.version_family_id = family.id
            source_document.version_number = 1
            source_document.is_current_version = True
            source_document.superseded_at = None

            previous_document = source_document

        versions = (
            Document.query
            .filter_by(
                version_family_id=family.id,
                project_id=source_document.project_id,
            )
            .order_by(
                Document.version_number.desc(),
                Document.id.desc(),
            )
            .all()
        )

        current_document = next(
            (
                item
                for item in versions
                if item.is_current_version
                and item.id != new_document.id
            ),
            previous_document,
        )

        max_version = max(
            [
                int(item.version_number or 0)
                for item in versions
                if item.id != new_document.id
            ]
            or [
                int(
                    previous_document.version_number
                    or 1
                )
            ]
        )

        next_version_number = max_version + 1

        # Defensive invariant repair: one family must have only one current
        # member after this transaction.
        for item in versions:
            if (
                item.id != new_document.id
                and item.is_current_version
            ):
                item.is_current_version = False
                item.superseded_at = datetime.utcnow()

        current_document.is_current_version = False
        current_document.superseded_at = datetime.utcnow()

        change_summary = detect_document_version_changes(
            old_text=current_document.extracted_text,
            new_text=new_document.extracted_text,
            old_file_fingerprint=old_file_fingerprint,
            new_file_fingerprint=new_file_fingerprint,
            from_document_id=current_document.id,
            from_version=int(
                current_document.version_number
                or max_version
                or 1
            ),
            to_document_id=new_document.id,
            to_version=next_version_number,
        )

        new_document.version_family_id = family.id
        new_document.version_number = next_version_number
        new_document.is_current_version = True
        new_document.superseded_at = None
        new_document.version_change_json = json.dumps(
            change_summary,
            ensure_ascii=False,
        )

        family.updated_at = datetime.utcnow()

        # Collections follow the logical current document, not a stale
        # historical row. Move memberships atomically when a new version
        # becomes current so multi-document retrieval keeps working.
        for collection_item in (
            DocumentCollectionItem.query
            .filter_by(document_id=current_document.id)
            .all()
        ):
            collection_item.document_id = new_document.id

        (
            outdated_analyses,
            outdated_questions,
            outdated_suggestions,
            outdated_project_questions,
        ) = _invalidate_superseded_results(
            document=current_document,
            owner_id=owner_id,
        )

        db.session.commit()

    except SQLAlchemyError as error:
        db.session.rollback()
        _cleanup_unlinked_upload(
            document_id=new_document.id,
            storage_key=upload_result.storage_key,
            storage=storage_service,
        )

        raise DocumentVersionPersistenceError(
            "The PDF was uploaded, but LifeOS could not save its version history."
        ) from error

    embeddings_succeeded = False
    embedding_message: str | None = None

    if (
        upload_result.extraction_succeeded
        and upload_result.indexing_succeeded
        and str(new_document.extracted_text or "").strip()
    ):
        try:
            embedded = ensure_owned_document_embeddings(
                document_id=new_document.id,
                user_id=owner_id,
            )
            embeddings_succeeded = True
            embedding_message = (
                f"Prepared {embedded.embedded_count} new semantic embedding"
                f"{'s' if embedded.embedded_count != 1 else ''}; "
                f"reused {embedded.reused_count}."
            )

        except DocumentEmbeddingError as error:
            # Version activation remains valid. Hybrid retrieval can keep using
            # keyword search and regenerate embeddings lazily on the next use.
            embedding_message = str(error)

    return CreatedDocumentVersion(
        upload_result=upload_result,
        family=family,
        previous_document=current_document,
        current_document=new_document,
        change_summary=change_summary,
        outdated_analyses=outdated_analyses,
        outdated_questions=outdated_questions,
        outdated_suggestions=outdated_suggestions,
        outdated_project_questions=outdated_project_questions,
        embeddings_succeeded=embeddings_succeeded,
        embedding_message=embedding_message,
    )



def detect_document_version_changes(
    *,
    old_text: str | None,
    new_text: str | None,
    old_file_fingerprint: str | None = None,
    new_file_fingerprint: str | None = None,
    from_document_id: int,
    from_version: int,
    to_document_id: int,
    to_version: int,
) -> dict[str, Any]:
    """Detect page-level changes using normalized content fingerprints."""

    old_clean = str(old_text or "").strip()
    new_clean = str(new_text or "").strip()

    old_pages = _split_pages(old_clean)
    new_pages = _split_pages(new_clean)

    all_pages = sorted(
        set(old_pages)
        | set(new_pages)
    )

    changed_pages: list[int] = []
    added_pages: list[int] = []
    removed_pages: list[int] = []
    unchanged_pages: list[int] = []

    for page in all_pages:
        if page not in old_pages:
            added_pages.append(page)
            continue

        if page not in new_pages:
            removed_pages.append(page)
            continue

        if _text_fingerprint(old_pages[page]) == _text_fingerprint(new_pages[page]):
            unchanged_pages.append(page)
        else:
            changed_pages.append(page)

    old_fingerprint = _text_fingerprint(old_clean)
    new_fingerprint = _text_fingerprint(new_clean)

    return {
        "schema_version": VERSIONING_SCHEMA_VERSION,
        "from_document_id": from_document_id,
        "from_version": from_version,
        "to_document_id": to_document_id,
        "to_version": to_version,
        "content_changed": (
            old_fingerprint != new_fingerprint
            or (
                bool(old_file_fingerprint)
                and bool(new_file_fingerprint)
                and old_file_fingerprint != new_file_fingerprint
            )
        ),
        "old_fingerprint": old_fingerprint,
        "new_fingerprint": new_fingerprint,
        "old_file_fingerprint": old_file_fingerprint,
        "new_file_fingerprint": new_file_fingerprint,
        "changed_pages": changed_pages,
        "added_pages": added_pages,
        "removed_pages": removed_pages,
        "unchanged_pages": unchanged_pages,
        "changed_page_count": len(changed_pages),
        "added_page_count": len(added_pages),
        "removed_page_count": len(removed_pages),
        "unchanged_page_count": len(unchanged_pages),
    }



def _invalidate_superseded_results(
    *,
    document: Document,
    owner_id: int,
) -> tuple[int, int, int, int]:
    """Mark information derived from the superseded current source outdated."""

    outdated_analyses = (
        DocumentAIAnalysis.query
        .filter_by(
            document_id=document.id,
            user_id=owner_id,
            status="Completed",
        )
        .update(
            {"status": "Outdated"},
            synchronize_session=False,
        )
    )

    outdated_questions = (
        DocumentQuestion.query
        .filter_by(
            document_id=document.id,
            user_id=owner_id,
            status="Completed",
        )
        .update(
            {"status": "Outdated"},
            synchronize_session=False,
        )
    )

    outdated_suggestions = (
        DocumentTaskSuggestion.query
        .filter_by(
            document_id=document.id,
            user_id=owner_id,
            status="Pending",
        )
        .update(
            {"status": "Outdated"},
            synchronize_session=False,
        )
    )

    # Project-wide RAG depended on the current corpus. Once one current source
    # changes, previous completed project answers are historical, not current.
    outdated_project_questions = (
        ProjectQuestion.query
        .filter_by(
            project_id=document.project_id,
            user_id=owner_id,
            status="Completed",
        )
        .update(
            {"status": "Outdated"},
            synchronize_session=False,
        )
    )

    return (
        int(outdated_analyses or 0),
        int(outdated_questions or 0),
        int(outdated_suggestions or 0),
        int(outdated_project_questions or 0),
    )



def _split_pages(text: str) -> dict[int, str]:
    """Return extracted text by page, with a whole-document fallback."""

    cleaned = str(text or "").strip()

    if not cleaned:
        return {}

    matches = list(
        PAGE_MARKER_PATTERN.finditer(
            cleaned
        )
    )

    if not matches:
        return {1: cleaned}

    pages: dict[int, str] = {}

    for index, match in enumerate(matches):
        page = int(
            match.group(1)
        )
        start = match.end()
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(cleaned)
        )
        pages[page] = cleaned[
            start:end
        ].strip()

    return pages



def _text_fingerprint(value: str) -> str:
    normalized = "\n".join(
        line.rstrip()
        for line in str(value or "").replace(
            "\r\n",
            "\n",
        ).replace(
            "\r",
            "\n",
        ).split("\n")
    ).strip()

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()



def _family_name(filename: str) -> str:
    raw = str(filename or "").strip()

    if not raw:
        return "Document"

    try:
        stem = PurePath(raw).stem
    except Exception:
        stem = raw

    return (stem or raw)[:255]



def _storage_fingerprint(
    storage: StorageService,
    storage_key: str | None,
) -> str | None:
    key = str(storage_key or "").strip()

    if not key:
        return None

    digest = hashlib.sha256()

    try:
        with storage.open(
            key,
            "rb",
        ) as stream:
            while True:
                block = stream.read(
                    1024 * 1024
                )

                if not block:
                    break

                digest.update(block)

    except StorageError:
        return None

    return digest.hexdigest()


def _cleanup_unlinked_upload(
    *,
    document_id: int,
    storage_key: str,
    storage: StorageService,
) -> None:
    """Best-effort cleanup when version linking fails after PDF upload."""

    try:
        document = db.session.get(
            Document,
            document_id,
        )

        if document is not None:
            db.session.delete(document)
            db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()

    try:
        storage.delete(
            storage_key
        )
    except StorageError:
        pass

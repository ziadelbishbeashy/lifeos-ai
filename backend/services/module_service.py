"""Modules V1 domain service.

A Module is a knowledge-driven workspace. It reuses the existing user-owned
Documents, Notes, Tasks, Collections, and Document Brain infrastructure rather
than cloning Project behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from werkzeug.datastructures import FileStorage

from database import db
from models import (
    Document,
    DocumentCollection,
    LearningModule,
    Lecture,
    ModuleCollectionLink,
    ModuleDocumentLink,
    ModuleNoteLink,
    ModuleQuestion,
    ModuleTaskLink,
    Note,
    Task,
)
from services.document_access_service import DocumentNotFoundError, require_owned_document
from services.document_collection_service import DocumentCollectionNotFoundError, require_owned_collection
from services.document_service import CreatedProjectDocument, create_project_pdf_document
from storage.base import StorageService


MODULE_STATUSES = {"Active", "Archived"}
LECTURE_STATUSES = {"Planned", "In Progress", "Completed"}


class ModuleError(RuntimeError):
    pass


class ModuleNotFoundError(ModuleError, LookupError):
    pass


class ModuleValidationError(ModuleError, ValueError):
    pass


class ModulePersistenceError(ModuleError):
    pass


@dataclass(frozen=True)
class UploadedModuleDocument:
    upload: CreatedProjectDocument
    link: ModuleDocumentLink


def list_owned_modules(user_id: int) -> list[LearningModule]:
    return (
        LearningModule.query
        .filter_by(user_id=user_id)
        .order_by(LearningModule.updated_at.desc(), LearningModule.id.desc())
        .all()
    )


def require_owned_module(module_id: int, user_id: int) -> LearningModule:
    module = LearningModule.query.filter_by(id=module_id, user_id=user_id).first()
    if module is None:
        raise ModuleNotFoundError("Module not found.")
    return module


def create_module(
    *,
    user_id: int,
    title: Any,
    description: Any = None,
    subject: Any = None,
    status: Any = "Active",
) -> LearningModule:
    module = LearningModule(
        user_id=user_id,
        title=_required_text(title, "Module title", 150),
        description=_optional_text(description, 6000),
        subject=_optional_text(subject, 150),
        status=_module_status(status),
    )
    return _commit(module, "LifeOS could not create the module.")


def update_module(
    *,
    module_id: int,
    user_id: int,
    title: Any = None,
    description: Any = None,
    subject: Any = None,
    status: Any = None,
    provided_fields: set[str] | None = None,
) -> LearningModule:
    module = require_owned_module(module_id, user_id)
    fields = provided_fields or set()
    if "title" in fields:
        module.title = _required_text(title, "Module title", 150)
    if "description" in fields:
        module.description = _optional_text(description, 6000)
    if "subject" in fields:
        module.subject = _optional_text(subject, 150)
    if "status" in fields:
        module.status = _module_status(status)
    return _commit(module, "LifeOS could not update the module.")


def delete_module(*, module_id: int, user_id: int) -> str:
    module = require_owned_module(module_id, user_id)
    title = module.title
    try:
        db.session.delete(module)
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise ModulePersistenceError("LifeOS could not delete the module.") from error
    return title


def require_owned_lecture(*, module_id: int, lecture_id: int, user_id: int) -> Lecture:
    module = require_owned_module(module_id, user_id)
    lecture = Lecture.query.filter_by(id=lecture_id, module_id=module.id).first()
    if lecture is None:
        raise ModuleNotFoundError("Lecture not found.")
    return lecture


def create_lecture(
    *,
    module_id: int,
    user_id: int,
    title: Any,
    lecture_number: Any = None,
    lecture_date: Any = None,
    status: Any = "Planned",
    topics: Any = None,
    summary: Any = None,
) -> Lecture:
    module = require_owned_module(module_id, user_id)
    number = _lecture_number(lecture_number)
    _ensure_lecture_number_available(module.id, number)
    lecture = Lecture(
        module_id=module.id,
        title=_required_text(title, "Lecture title", 180),
        lecture_number=number,
        lecture_date=_date_value(lecture_date),
        status=_lecture_status(status),
        topics=_optional_text(topics, 5000),
        summary=_optional_text(summary, 8000),
    )
    return _commit(lecture, "LifeOS could not create the lecture.")


def update_lecture(
    *,
    module_id: int,
    lecture_id: int,
    user_id: int,
    payload: dict[str, Any],
) -> Lecture:
    lecture = require_owned_lecture(module_id=module_id, lecture_id=lecture_id, user_id=user_id)
    if "title" in payload:
        lecture.title = _required_text(payload.get("title"), "Lecture title", 180)
    if "lecture_number" in payload:
        number = _lecture_number(payload.get("lecture_number"))
        _ensure_lecture_number_available(module_id, number, exclude_lecture_id=lecture.id)
        lecture.lecture_number = number
    if "lecture_date" in payload:
        lecture.lecture_date = _date_value(payload.get("lecture_date"))
    if "status" in payload:
        lecture.status = _lecture_status(payload.get("status"))
    if "topics" in payload:
        lecture.topics = _optional_text(payload.get("topics"), 5000)
    if "summary" in payload:
        lecture.summary = _optional_text(payload.get("summary"), 8000)
    return _commit(lecture, "LifeOS could not update the lecture.")


def delete_lecture(*, module_id: int, lecture_id: int, user_id: int) -> str:
    lecture = require_owned_lecture(module_id=module_id, lecture_id=lecture_id, user_id=user_id)
    title = lecture.title
    try:
        ModuleDocumentLink.query.filter_by(module_id=module_id, lecture_id=lecture.id).update({"lecture_id": None})
        ModuleNoteLink.query.filter_by(module_id=module_id, lecture_id=lecture.id).update({"lecture_id": None})
        ModuleTaskLink.query.filter_by(module_id=module_id, lecture_id=lecture.id).update({"lecture_id": None})
        ModuleQuestion.query.filter_by(module_id=module_id, lecture_id=lecture.id).update({"lecture_id": None})
        db.session.delete(lecture)
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise ModulePersistenceError("LifeOS could not delete the lecture.") from error
    return title


def link_document(
    *,
    module_id: int,
    document_id: int,
    user_id: int,
    lecture_id: int | None = None,
) -> ModuleDocumentLink:
    module = require_owned_module(module_id, user_id)
    try:
        document = require_owned_document(document_id, user_id)
    except DocumentNotFoundError as error:
        raise ModuleNotFoundError("Document not found.") from error
    if not bool(document.is_current_version):
        raise ModuleValidationError("Link the current version of this document to the module.")
    lecture = _optional_owned_lecture(module.id, lecture_id, user_id)

    link = ModuleDocumentLink.query.filter_by(module_id=module.id, document_id=document.id).first()
    if link is None:
        link = ModuleDocumentLink(
            module_id=module.id,
            document_id=document.id,
            lecture_id=lecture.id if lecture is not None else None,
        )
        return _commit(link, "LifeOS could not link the document to the module.")

    link.lecture_id = lecture.id if lecture is not None else None
    return _commit(link, "LifeOS could not update the document's lecture link.")


def unlink_document(*, module_id: int, document_id: int, user_id: int) -> None:
    module = require_owned_module(module_id, user_id)
    link = ModuleDocumentLink.query.filter_by(module_id=module.id, document_id=document_id).first()
    if link is None:
        raise ModuleNotFoundError("The document is not linked to this module.")
    _delete(link, "LifeOS could not remove the document from the module.")


def upload_module_document(
    upload: FileStorage | None,
    *,
    module_id: int,
    user_id: int,
    lecture_id: int | None,
    max_bytes: int,
    storage: StorageService | None = None,
) -> UploadedModuleDocument:
    module = require_owned_module(module_id, user_id)
    lecture = _optional_owned_lecture(module.id, lecture_id, user_id)
    uploaded = create_project_pdf_document(
        upload,
        owner_id=user_id,
        project_id=None,
        max_bytes=max_bytes,
        storage=storage,
    )
    link = link_document(
        module_id=module.id,
        document_id=uploaded.document.id,
        user_id=user_id,
        lecture_id=lecture.id if lecture is not None else None,
    )
    return UploadedModuleDocument(upload=uploaded, link=link)


def link_note(*, module_id: int, note_id: int, user_id: int, lecture_id: int | None = None) -> ModuleNoteLink:
    module = require_owned_module(module_id, user_id)
    note = Note.query.filter_by(id=note_id, user_id=user_id).first()
    if note is None:
        raise ModuleNotFoundError("Note not found.")
    lecture = _optional_owned_lecture(module.id, lecture_id, user_id)
    link = ModuleNoteLink.query.filter_by(module_id=module.id, note_id=note.id).first()
    if link is None:
        link = ModuleNoteLink(module_id=module.id, note_id=note.id, lecture_id=lecture.id if lecture else None)
    else:
        link.lecture_id = lecture.id if lecture else None
    return _commit(link, "LifeOS could not link the note to the module.")


def unlink_note(*, module_id: int, note_id: int, user_id: int) -> None:
    module = require_owned_module(module_id, user_id)
    link = ModuleNoteLink.query.filter_by(module_id=module.id, note_id=note_id).first()
    if link is None:
        raise ModuleNotFoundError("The note is not linked to this module.")
    _delete(link, "LifeOS could not remove the note from the module.")


def link_task(*, module_id: int, task_id: int, user_id: int, lecture_id: int | None = None) -> ModuleTaskLink:
    module = require_owned_module(module_id, user_id)
    task = Task.query.filter_by(id=task_id, user_id=user_id).first()
    if task is None:
        raise ModuleNotFoundError("Task not found.")
    lecture = _optional_owned_lecture(module.id, lecture_id, user_id)
    link = ModuleTaskLink.query.filter_by(module_id=module.id, task_id=task.id).first()
    if link is None:
        link = ModuleTaskLink(module_id=module.id, task_id=task.id, lecture_id=lecture.id if lecture else None)
    else:
        link.lecture_id = lecture.id if lecture else None
    return _commit(link, "LifeOS could not link the task to the module.")


def unlink_task(*, module_id: int, task_id: int, user_id: int) -> None:
    module = require_owned_module(module_id, user_id)
    link = ModuleTaskLink.query.filter_by(module_id=module.id, task_id=task_id).first()
    if link is None:
        raise ModuleNotFoundError("The task is not linked to this module.")
    _delete(link, "LifeOS could not remove the task from the module.")


def link_collection(*, module_id: int, collection_id: int, user_id: int) -> ModuleCollectionLink:
    module = require_owned_module(module_id, user_id)
    try:
        collection = require_owned_collection(collection_id, user_id)
    except DocumentCollectionNotFoundError as error:
        raise ModuleNotFoundError("Collection not found.") from error
    link = ModuleCollectionLink.query.filter_by(module_id=module.id, collection_id=collection.id).first()
    if link is not None:
        return link
    link = ModuleCollectionLink(module_id=module.id, collection_id=collection.id)
    return _commit(link, "LifeOS could not link the collection to the module.")


def unlink_collection(*, module_id: int, collection_id: int, user_id: int) -> None:
    module = require_owned_module(module_id, user_id)
    link = ModuleCollectionLink.query.filter_by(module_id=module.id, collection_id=collection_id).first()
    if link is None:
        raise ModuleNotFoundError("The collection is not linked to this module.")
    _delete(link, "LifeOS could not remove the collection from the module.")


def module_documents(module: LearningModule, *, lecture_id: int | None = None) -> list[Document]:
    links = list(module.document_links or [])
    if lecture_id is not None:
        links = [link for link in links if link.lecture_id == lecture_id]
    docs = [link.document for link in links if getattr(link, "document", None) is not None]
    return [doc for doc in docs if bool(getattr(doc, "is_current_version", True))]


def _optional_owned_lecture(module_id: int, lecture_id: int | None, user_id: int) -> Lecture | None:
    if lecture_id in (None, 0, ""):
        return None
    return require_owned_lecture(module_id=module_id, lecture_id=int(lecture_id), user_id=user_id)


def _ensure_lecture_number_available(module_id: int, number: int | None, exclude_lecture_id: int | None = None) -> None:
    if number is None:
        return
    query = Lecture.query.filter_by(module_id=module_id, lecture_number=number)
    if exclude_lecture_id is not None:
        query = query.filter(Lecture.id != exclude_lecture_id)
    if query.first() is not None:
        raise ModuleValidationError(f"Lecture {number} already exists in this module.")


def _required_text(value: Any, label: str, max_length: int) -> str:
    cleaned = " ".join(str(value or "").split()).strip()
    if not cleaned:
        raise ModuleValidationError(f"{label} is required.")
    if len(cleaned) > max_length:
        raise ModuleValidationError(f"{label} cannot exceed {max_length} characters.")
    return cleaned


def _optional_text(value: Any, max_length: int) -> str | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    if len(cleaned) > max_length:
        raise ModuleValidationError(f"Text cannot exceed {max_length} characters.")
    return cleaned


def _module_status(value: Any) -> str:
    cleaned = " ".join(str(value or "Active").split()).strip().title()
    if cleaned not in MODULE_STATUSES:
        raise ModuleValidationError("Module status must be Active or Archived.")
    return cleaned


def _lecture_status(value: Any) -> str:
    cleaned = " ".join(str(value or "Planned").split()).strip().title()
    if cleaned not in LECTURE_STATUSES:
        raise ModuleValidationError("Lecture status must be Planned, In Progress, or Completed.")
    return cleaned


def _lecture_number(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ModuleValidationError("Lecture number must be a positive whole number.") from error
    if number <= 0:
        raise ModuleValidationError("Lecture number must be a positive whole number.")
    return number


def _date_value(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as error:
        raise ModuleValidationError("Use a valid lecture date.") from error


def _commit(value, message: str):
    try:
        db.session.add(value)
        db.session.commit()
        return value
    except SQLAlchemyError as error:
        db.session.rollback()
        raise ModulePersistenceError(message) from error


def _delete(value, message: str) -> None:
    try:
        db.session.delete(value)
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise ModulePersistenceError(message) from error

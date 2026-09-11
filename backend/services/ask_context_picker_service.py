"""I16.1 explicit Ask LifeOS context selection.

The picker is an authenticated convenience layer, never an authority boundary.
Every selected resource is revalidated against the current owner before a chat
request can use it. V1 intentionally keeps one active context at a time so the
retrieval scope is obvious to the user; multi-context comparison can be added
later on top of the same validation contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from models import Document, DocumentCollection, LearningModule, Lecture, Project
from services.document_access_service import list_owned_documents
from services.document_collection_service import list_owned_collections
from services.module_service import list_owned_modules
from services.project_service import list_owned_projects


SUPPORTED_CONTEXT_TYPES = {"project", "document", "module", "lecture", "collection"}
MAX_CONTEXT_OPTIONS_PER_GROUP = 40


class AskContextValidationError(ValueError):
    pass


class AskContextNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class AskContextOption:
    type: str
    id: int
    label: str
    subtitle: str | None = None
    parent_type: str | None = None
    parent_id: int | None = None
    parent_label: str | None = None
    project_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "label": self.label,
            "subtitle": self.subtitle,
            "parent": (
                {
                    "type": self.parent_type,
                    "id": self.parent_id,
                    "label": self.parent_label,
                }
                if self.parent_type and self.parent_id is not None
                else None
            ),
            "project_id": self.project_id,
        }


def _document_option(document: Document, project_titles: dict[int, str]) -> AskContextOption:
    project_id = int(document.project_id) if document.project_id is not None else None
    project_title = project_titles.get(project_id) if project_id is not None else None
    return AskContextOption(
        type="document",
        id=int(document.id),
        label=str(document.filename or f"Document {document.id}"),
        subtitle=project_title or "Document Brain",
        parent_type="project" if project_id is not None else None,
        parent_id=project_id,
        parent_label=project_title,
        project_id=project_id,
    )


def list_owned_ask_context_options(*, owner_id: int) -> dict[str, Any]:
    projects = list_owned_projects(int(owner_id))
    project_titles = {int(item.id): str(item.title) for item in projects}
    project_items = [
        AskContextOption(
            type="project",
            id=int(item.id),
            label=str(item.title),
            subtitle=str(item.status or "Project"),
            project_id=int(item.id),
        )
        for item in projects[:MAX_CONTEXT_OPTIONS_PER_GROUP]
    ]

    documents = [
        item for item in list_owned_documents(int(owner_id))
        if bool(getattr(item, "is_current_version", True))
    ][:MAX_CONTEXT_OPTIONS_PER_GROUP]
    document_items = [_document_option(item, project_titles) for item in documents]

    modules = list_owned_modules(int(owner_id))[:MAX_CONTEXT_OPTIONS_PER_GROUP]
    module_items: list[AskContextOption] = []
    lecture_items: list[AskContextOption] = []
    for module in modules:
        module_items.append(
            AskContextOption(
                type="module",
                id=int(module.id),
                label=str(module.title),
                subtitle=str(module.subject or module.status or "Module"),
            )
        )
        for lecture in list(module.lectures or []):
            if len(lecture_items) >= MAX_CONTEXT_OPTIONS_PER_GROUP:
                break
            number = f"Lecture {lecture.lecture_number}" if lecture.lecture_number is not None else "Lecture"
            lecture_items.append(
                AskContextOption(
                    type="lecture",
                    id=int(lecture.id),
                    label=str(lecture.title),
                    subtitle=f"{module.title} · {number}",
                    parent_type="module",
                    parent_id=int(module.id),
                    parent_label=str(module.title),
                )
            )

    collections = list_owned_collections(int(owner_id))[:MAX_CONTEXT_OPTIONS_PER_GROUP]
    collection_items = [
        AskContextOption(
            type="collection",
            id=int(item.id),
            label=str(item.name),
            subtitle="Document collection",
        )
        for item in collections
    ]

    return {
        "groups": {
            "projects": [item.to_dict() for item in project_items],
            "documents": [item.to_dict() for item in document_items],
            "modules": [item.to_dict() for item in module_items],
            "lectures": [item.to_dict() for item in lecture_items],
            "collections": [item.to_dict() for item in collection_items],
        },
        "counts": {
            "projects": len(project_items),
            "documents": len(document_items),
            "modules": len(module_items),
            "lectures": len(lecture_items),
            "collections": len(collection_items),
        },
        "selection_mode": "single",
        "verified_ownership": True,
    }


def validate_owned_ask_context(*, owner_id: int, raw_context: Any) -> AskContextOption | None:
    if raw_context in (None, "", {}):
        return None
    if not isinstance(raw_context, dict):
        raise AskContextValidationError("Invalid Ask LifeOS context.")

    kind = str(raw_context.get("type") or "").strip().lower()
    if kind not in SUPPORTED_CONTEXT_TYPES:
        raise AskContextValidationError("Unsupported Ask LifeOS context type.")
    try:
        resource_id = int(raw_context.get("id"))
    except (TypeError, ValueError) as error:
        raise AskContextValidationError("Invalid Ask LifeOS context ID.") from error
    if resource_id <= 0:
        raise AskContextValidationError("Invalid Ask LifeOS context ID.")

    owner_id = int(owner_id)
    if kind == "project":
        row = Project.query.filter_by(id=resource_id, user_id=owner_id).first()
        if row is None:
            raise AskContextNotFoundError("Selected project not found.")
        return AskContextOption("project", row.id, row.title, row.status, project_id=row.id)

    if kind == "document":
        row = Document.query.filter_by(id=resource_id, user_id=owner_id).first()
        if row is None or not bool(getattr(row, "is_current_version", True)):
            raise AskContextNotFoundError("Selected document not found.")
        project = None
        if row.project_id is not None:
            project = Project.query.filter_by(id=row.project_id, user_id=owner_id).first()
        return AskContextOption(
            "document",
            row.id,
            row.filename,
            project.title if project is not None else "Document Brain",
            "project" if project is not None else None,
            project.id if project is not None else None,
            project.title if project is not None else None,
            project.id if project is not None else None,
        )

    if kind == "module":
        row = LearningModule.query.filter_by(id=resource_id, user_id=owner_id).first()
        if row is None:
            raise AskContextNotFoundError("Selected module not found.")
        return AskContextOption("module", row.id, row.title, row.subject or row.status)

    if kind == "lecture":
        row = (
            Lecture.query
            .join(LearningModule, LearningModule.id == Lecture.module_id)
            .filter(Lecture.id == resource_id, LearningModule.user_id == owner_id)
            .first()
        )
        if row is None:
            raise AskContextNotFoundError("Selected lecture not found.")
        module = row.module
        number = f"Lecture {row.lecture_number}" if row.lecture_number is not None else "Lecture"
        return AskContextOption(
            "lecture",
            row.id,
            row.title,
            f"{module.title} · {number}",
            "module",
            module.id,
            module.title,
        )

    row = DocumentCollection.query.filter_by(id=resource_id, user_id=owner_id).first()
    if row is None:
        raise AskContextNotFoundError("Selected collection not found.")
    return AskContextOption("collection", row.id, row.name, "Document collection")

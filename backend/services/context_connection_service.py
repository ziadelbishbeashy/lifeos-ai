"""I13 — first-class, ownership-bounded context connections.

LifeOS already has several structural relationships (Project ownership, Module
links, Collections).  I13 exposes them through one verified connection graph and
adds a small persisted edge table for provenance that does not naturally fit an
existing domain table — most importantly, work created from Ask LifeOS evidence.

The LLM never chooses or writes links.  Persisted links are created only from
already-confirmed deterministic actions or future explicit user workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import json
import re
import unicodedata
from typing import Any, Iterable

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from database import db
from models import (
    AITaskSuggestion,
    Document,
    DocumentAIAnalysis,
    DocumentTaskSuggestion,
    DocumentCollection,
    DocumentCollectionItem,
    LearningModule,
    Lecture,
    LifeOSActionProposal,
    LifeOSContextLink,
    ModuleCollectionLink,
    ModuleDocumentLink,
    ModuleNoteLink,
    ModuleTaskLink,
    Note,
    Project,
    Task,
)


SUPPORTED_RESOURCE_TYPES = frozenset({
    "project", "task", "note", "document", "module", "lecture", "collection", "document_analysis",
})
ALLOWED_RELATION_TYPES = frozenset({
    "derived_from", "related_to", "supports", "references", "analysis_of",
})
MAX_CONNECTIONS = 30
MAX_RESOLUTION_CANDIDATES = 6


class ContextConnectionError(RuntimeError):
    pass


class ContextConnectionValidationError(ContextConnectionError, ValueError):
    pass


class ContextConnectionNotFoundError(ContextConnectionError, LookupError):
    pass


@dataclass(frozen=True)
class ContextResource:
    resource_type: str
    resource_id: int
    label: str
    url: str | None
    project_id: int | None = None
    project_title: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.resource_type,
            "id": self.resource_id,
            "label": self.label,
            "url": self.url,
            "project_id": self.project_id,
            "project_title": self.project_title,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ContextConnection:
    relation_type: str
    relation_label: str
    resource: ContextResource
    reason: str | None
    provenance_type: str
    provenance_id: int | None
    evidence: tuple[dict[str, Any], ...] = ()
    persisted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "relation_type": self.relation_type,
            "relation_label": self.relation_label,
            "resource": self.resource.to_dict(),
            "reason": self.reason,
            "provenance": {"type": self.provenance_type, "id": self.provenance_id},
            "evidence": list(self.evidence),
            "persisted": self.persisted,
        }


@dataclass(frozen=True)
class ContextConnectionsResult:
    resource: ContextResource | None
    summary: str
    connections: tuple[ContextConnection, ...]
    candidates: tuple[ContextResource, ...] = ()
    context_limited: bool = False

    def to_dict(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for item in self.connections:
            resource_type = item.resource.resource_type
            counts[resource_type] = counts.get(resource_type, 0) + 1
        return {
            "resource": self.resource.to_dict() if self.resource else None,
            "summary": self.summary,
            "connections": [item.to_dict() for item in self.connections],
            "candidates": [item.to_dict() for item in self.candidates],
            "counts": counts,
            "context_limited": self.context_limited,
            "verified_from_state": True,
            "read_only": True,
        }


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace("’", "'")
    text = re.sub(r"[^a-z0-9+#._' -]+", " ", text)
    return " ".join(text.split())


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _project_title(project_id: int | None, owner_id: int) -> str | None:
    if project_id is None:
        return None
    project = Project.query.filter_by(id=int(project_id), user_id=int(owner_id)).first()
    return str(project.title) if project else None


def require_owned_context_resource(*, owner_id: int, resource_type: str, resource_id: int) -> ContextResource:
    kind = str(resource_type or "").strip().casefold()
    if kind not in SUPPORTED_RESOURCE_TYPES:
        raise ContextConnectionValidationError("This LifeOS resource type is not supported for context connections.")
    try:
        rid = int(resource_id)
    except (TypeError, ValueError) as error:
        raise ContextConnectionValidationError("A valid LifeOS resource id is required.") from error

    if kind == "project":
        item = Project.query.filter_by(id=rid, user_id=owner_id).first()
        if not item:
            raise ContextConnectionNotFoundError("Resource not found.")
        return ContextResource(kind, rid, item.title, f"/projects/{rid}", rid, item.title, item.status)

    if kind == "task":
        item = Task.query.filter_by(id=rid, user_id=owner_id).first()
        if not item:
            raise ContextConnectionNotFoundError("Resource not found.")
        project_title = _project_title(item.project_id, owner_id)
        return ContextResource(kind, rid, item.title, "/tasks", item.project_id, project_title, item.status)

    if kind == "note":
        item = Note.query.filter_by(id=rid, user_id=owner_id).first()
        if not item:
            raise ContextConnectionNotFoundError("Resource not found.")
        project_title = _project_title(item.project_id, owner_id)
        return ContextResource(kind, rid, item.title, f"/notes/{rid}", item.project_id, project_title, item.note_type)

    if kind == "document":
        item = Document.query.filter_by(id=rid, user_id=owner_id).first()
        if not item:
            raise ContextConnectionNotFoundError("Resource not found.")
        project_title = _project_title(item.project_id, owner_id)
        detail = "Current version" if bool(getattr(item, "is_current_version", True)) else "Historical version"
        return ContextResource(kind, rid, item.filename, f"/documents/{rid}", item.project_id, project_title, detail)

    if kind == "module":
        item = LearningModule.query.filter_by(id=rid, user_id=owner_id).first()
        if not item:
            raise ContextConnectionNotFoundError("Resource not found.")
        return ContextResource(kind, rid, item.title, f"/modules/{rid}", None, None, item.subject or item.status)

    if kind == "lecture":
        item = (
            Lecture.query.join(LearningModule, LearningModule.id == Lecture.module_id)
            .filter(Lecture.id == rid, LearningModule.user_id == owner_id)
            .first()
        )
        if not item:
            raise ContextConnectionNotFoundError("Resource not found.")
        number = f"Lecture {item.lecture_number}: " if item.lecture_number else ""
        return ContextResource(kind, rid, f"{number}{item.title}", f"/modules/{item.module_id}", None, None, item.status)

    if kind == "collection":
        item = DocumentCollection.query.filter_by(id=rid, user_id=owner_id).first()
        if not item:
            raise ContextConnectionNotFoundError("Resource not found.")
        return ContextResource(kind, rid, item.name, "/documents/collections", None, None, item.description)

    analysis = DocumentAIAnalysis.query.filter_by(id=rid, user_id=owner_id).first()
    if not analysis:
        raise ContextConnectionNotFoundError("Resource not found.")
    document = Document.query.filter_by(id=analysis.document_id, user_id=owner_id).first()
    if not document:
        raise ContextConnectionNotFoundError("Resource not found.")
    project_title = _project_title(document.project_id, owner_id)
    return ContextResource(
        kind, rid, f"Analysis of {document.filename}", f"/documents/{document.id}",
        document.project_id, project_title, analysis.status,
    )


def create_owned_context_link(
    *,
    owner_id: int,
    source_type: str,
    source_id: int,
    target_type: str,
    target_id: int,
    relation_type: str,
    reason: str | None = None,
    provenance_type: str = "user",
    provenance_id: int | None = None,
    evidence: Iterable[dict[str, Any]] | None = None,
    commit: bool = False,
) -> LifeOSContextLink:
    """Create one verified edge.  This function never trusts caller ownership."""

    source = require_owned_context_resource(owner_id=owner_id, resource_type=source_type, resource_id=source_id)
    target = require_owned_context_resource(owner_id=owner_id, resource_type=target_type, resource_id=target_id)
    relation = str(relation_type or "").strip().casefold()
    if relation not in ALLOWED_RELATION_TYPES:
        raise ContextConnectionValidationError("This LifeOS context relationship is not supported.")
    if source.resource_type == target.resource_type and source.resource_id == target.resource_id:
        raise ContextConnectionValidationError("A LifeOS resource cannot be linked to itself.")

    existing = LifeOSContextLink.query.filter_by(
        user_id=owner_id,
        source_type=source.resource_type,
        source_id=source.resource_id,
        target_type=target.resource_type,
        target_id=target.resource_id,
        relation_type=relation,
    ).first()
    if existing:
        return existing

    safe_evidence = []
    for raw in list(evidence or [])[:8]:
        if not isinstance(raw, dict):
            continue
        safe_evidence.append({
            "source_type": _clean(raw.get("source_type"), 40),
            "source_id": raw.get("source_id") if isinstance(raw.get("source_id"), int) else None,
            "label": _clean(raw.get("label"), 255),
            "field": _clean(raw.get("field"), 120),
            "freshness": _clean(raw.get("freshness"), 40),
        })

    link = LifeOSContextLink(
        user_id=owner_id,
        source_type=source.resource_type,
        source_id=source.resource_id,
        target_type=target.resource_type,
        target_id=target.resource_id,
        relation_type=relation,
        reason=_clean(reason, 2000) or None,
        provenance_type=_clean(provenance_type, 48) or "user",
        provenance_id=int(provenance_id) if provenance_id is not None else None,
        evidence_json=json.dumps(safe_evidence, ensure_ascii=False),
    )
    db.session.add(link)
    if commit:
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            duplicate = LifeOSContextLink.query.filter_by(
                user_id=owner_id,
                source_type=source.resource_type,
                source_id=source.resource_id,
                target_type=target.resource_type,
                target_id=target.resource_id,
                relation_type=relation,
            ).first()
            if duplicate:
                return duplicate
            raise
        except SQLAlchemyError as error:
            db.session.rollback()
            raise ContextConnectionError("LifeOS could not save the context connection.") from error
    return link


def persist_confirmed_action_connections(*, proposal: LifeOSActionProposal, resource_type: str, resource_id: int) -> int:
    """Persist provenance edges after a confirmed I9 action, without committing."""

    if proposal.status not in {"executing", "confirmed"}:
        return 0
    if resource_type not in {"task", "note", "document_analysis"}:
        return 0

    created = 0
    if resource_type == "document_analysis":
        document_id = proposal.payload.get("document_id")
        if document_id:
            existing = LifeOSContextLink.query.filter_by(
                user_id=proposal.user_id, source_type="document_analysis", source_id=resource_id,
                target_type="document", target_id=int(document_id), relation_type="analysis_of",
            ).first()
            if not existing:
                create_owned_context_link(
                    owner_id=proposal.user_id,
                    source_type="document_analysis", source_id=resource_id,
                    target_type="document", target_id=int(document_id), relation_type="analysis_of",
                    reason=proposal.reason, provenance_type="ask_lifeos", provenance_id=proposal.id,
                    evidence=proposal.evidence, commit=False,
                )
                created += 1
        return created

    for evidence in proposal.evidence[:8]:
        if not isinstance(evidence, dict):
            continue
        target_type = str(evidence.get("source_type") or "").strip().casefold()
        target_id = evidence.get("source_id")
        if target_type not in SUPPORTED_RESOURCE_TYPES or target_type == "project" or target_id is None:
            continue
        try:
            target_id = int(target_id)
            require_owned_context_resource(owner_id=proposal.user_id, resource_type=target_type, resource_id=target_id)
        except (TypeError, ValueError, ContextConnectionError):
            continue
        existing = LifeOSContextLink.query.filter_by(
            user_id=proposal.user_id,
            source_type=resource_type,
            source_id=resource_id,
            target_type=target_type,
            target_id=target_id,
            relation_type="derived_from",
        ).first()
        if existing:
            continue
        create_owned_context_link(
            owner_id=proposal.user_id,
            source_type=resource_type, source_id=resource_id,
            target_type=target_type, target_id=target_id,
            relation_type="derived_from",
            reason=proposal.reason,
            provenance_type="ask_lifeos", provenance_id=proposal.id,
            evidence=[evidence], commit=False,
        )
        created += 1
    return created


def _relation_label(relation_type: str, *, outgoing: bool) -> str:
    if outgoing:
        return {
            "derived_from": "Derived from",
            "related_to": "Related to",
            "supports": "Supports",
            "references": "References",
            "analysis_of": "Analysis of",
            "belongs_to_project": "Project",
            "module_resource": "Module",
            "lecture_resource": "Lecture",
            "collection_resource": "Collection",
            "contains": "Contains",
        }.get(relation_type, relation_type.replace("_", " ").title())
    return {
        "derived_from": "Generated from this",
        "related_to": "Related to",
        "supports": "Supported by this",
        "references": "Referenced by",
        "analysis_of": "Has analysis",
        "belongs_to_project": "Contains",
        "module_resource": "Linked resource",
        "lecture_resource": "Linked resource",
        "collection_resource": "Contains",
        "contains": "Belongs to",
    }.get(relation_type, relation_type.replace("_", " ").title())


def _connection(
    *,
    owner_id: int,
    relation_type: str,
    resource_type: str,
    resource_id: int,
    outgoing: bool,
    reason: str | None,
    provenance_type: str,
    provenance_id: int | None = None,
    evidence: Iterable[dict[str, Any]] | None = None,
    persisted: bool = False,
) -> ContextConnection | None:
    try:
        resource = require_owned_context_resource(
            owner_id=owner_id, resource_type=resource_type, resource_id=resource_id,
        )
    except ContextConnectionError:
        return None
    return ContextConnection(
        relation_type=relation_type,
        relation_label=_relation_label(relation_type, outgoing=outgoing),
        resource=resource,
        reason=_clean(reason, 1200) or None,
        provenance_type=provenance_type,
        provenance_id=provenance_id,
        evidence=tuple(item for item in list(evidence or [])[:8] if isinstance(item, dict)),
        persisted=persisted,
    )


def _persisted_connections(*, owner_id: int, resource_type: str, resource_id: int) -> list[ContextConnection]:
    links = LifeOSContextLink.query.filter(
        LifeOSContextLink.user_id == owner_id,
        or_(
            (LifeOSContextLink.source_type == resource_type) & (LifeOSContextLink.source_id == resource_id),
            (LifeOSContextLink.target_type == resource_type) & (LifeOSContextLink.target_id == resource_id),
        ),
    ).order_by(LifeOSContextLink.created_at.desc(), LifeOSContextLink.id.desc()).limit(MAX_CONNECTIONS * 2).all()
    result: list[ContextConnection] = []
    for link in links:
        outgoing = link.source_type == resource_type and int(link.source_id) == int(resource_id)
        other_type = link.target_type if outgoing else link.source_type
        other_id = link.target_id if outgoing else link.source_id
        item = _connection(
            owner_id=owner_id, relation_type=link.relation_type,
            resource_type=other_type, resource_id=other_id, outgoing=outgoing,
            reason=link.reason, provenance_type=link.provenance_type,
            provenance_id=link.provenance_id, evidence=link.evidence, persisted=True,
        )
        if item:
            result.append(item)
    return result


def _structural_connections(*, owner_id: int, resource: ContextResource) -> list[ContextConnection]:
    kind, rid = resource.resource_type, resource.resource_id
    result: list[ContextConnection] = []

    def add(relation: str, other_type: str, other_id: int, *, outgoing: bool = True, reason: str | None = None):
        item = _connection(
            owner_id=owner_id, relation_type=relation, resource_type=other_type, resource_id=other_id,
            outgoing=outgoing, reason=reason, provenance_type="workspace_state",
        )
        if item:
            result.append(item)

    if kind in {"task", "note", "document"} and resource.project_id is not None:
        add("belongs_to_project", "project", int(resource.project_id), reason="Direct project membership saved in LifeOS.")

    if kind == "task":
        for link in ModuleTaskLink.query.filter_by(task_id=rid).limit(MAX_CONNECTIONS).all():
            module = LearningModule.query.filter_by(id=link.module_id, user_id=owner_id).first()
            if not module:
                continue
            add("module_resource", "module", module.id, reason="Task is linked to this Module.")
            if link.lecture_id:
                add("lecture_resource", "lecture", link.lecture_id, reason="Task is linked to this Lecture.")

    elif kind == "note":
        for link in ModuleNoteLink.query.filter_by(note_id=rid).limit(MAX_CONNECTIONS).all():
            module = LearningModule.query.filter_by(id=link.module_id, user_id=owner_id).first()
            if not module:
                continue
            add("module_resource", "module", module.id, reason="Note is linked to this Module.")
            if link.lecture_id:
                add("lecture_resource", "lecture", link.lecture_id, reason="Note is linked to this Lecture.")

    elif kind == "document":
        for link in ModuleDocumentLink.query.filter_by(document_id=rid).limit(MAX_CONNECTIONS).all():
            module = LearningModule.query.filter_by(id=link.module_id, user_id=owner_id).first()
            if not module:
                continue
            add("module_resource", "module", module.id, reason="Document is linked to this Module.")
            if link.lecture_id:
                add("lecture_resource", "lecture", link.lecture_id, reason="Document is linked to this Lecture.")
        collection_rows = (
            DocumentCollectionItem.query.join(DocumentCollection, DocumentCollection.id == DocumentCollectionItem.collection_id)
            .filter(DocumentCollectionItem.document_id == rid, DocumentCollection.user_id == owner_id)
            .limit(MAX_CONNECTIONS).all()
        )
        for row in collection_rows:
            add("collection_resource", "collection", row.collection_id, reason="Document belongs to this Collection.")

    elif kind == "project":
        for task in Task.query.filter_by(user_id=owner_id, project_id=rid).order_by(Task.id.desc()).limit(10).all():
            add("contains", "task", task.id, reason="Task belongs to this Project.")
        for note in Note.query.filter_by(user_id=owner_id, project_id=rid).order_by(Note.id.desc()).limit(8).all():
            add("contains", "note", note.id, reason="Note belongs to this Project.")
        for document in Document.query.filter_by(user_id=owner_id, project_id=rid, is_current_version=True).order_by(Document.id.desc()).limit(12).all():
            add("contains", "document", document.id, reason="Current document belongs to this Project.")

    elif kind == "module":
        module = LearningModule.query.filter_by(id=rid, user_id=owner_id).first()
        if module:
            for lecture in list(module.lectures or [])[:12]:
                add("contains", "lecture", lecture.id, reason="Lecture belongs to this Module.")
            for link in list(module.document_links or [])[:12]:
                add("module_resource", "document", link.document_id, reason="Document is linked to this Module.")
            for link in list(module.note_links or [])[:10]:
                add("module_resource", "note", link.note_id, reason="Note is linked to this Module.")
            for link in list(module.task_links or [])[:10]:
                add("module_resource", "task", link.task_id, reason="Task is linked to this Module.")
            for link in list(module.collection_links or [])[:8]:
                add("module_resource", "collection", link.collection_id, reason="Collection is linked to this Module.")

    elif kind == "lecture":
        lecture = (
            Lecture.query.join(LearningModule, LearningModule.id == Lecture.module_id)
            .filter(Lecture.id == rid, LearningModule.user_id == owner_id).first()
        )
        if lecture:
            add("belongs_to_project", "module", lecture.module_id, reason="Lecture belongs to this Module.")
            for link in ModuleDocumentLink.query.filter_by(lecture_id=rid).limit(10).all():
                add("lecture_resource", "document", link.document_id, reason="Document is linked to this Lecture.")
            for link in ModuleNoteLink.query.filter_by(lecture_id=rid).limit(10).all():
                add("lecture_resource", "note", link.note_id, reason="Note is linked to this Lecture.")
            for link in ModuleTaskLink.query.filter_by(lecture_id=rid).limit(10).all():
                add("lecture_resource", "task", link.task_id, reason="Task is linked to this Lecture.")

    elif kind == "collection":
        collection = DocumentCollection.query.filter_by(id=rid, user_id=owner_id).first()
        if collection:
            for row in list(collection.items or [])[:15]:
                add("collection_resource", "document", row.document_id, reason="Document belongs to this Collection.")
            for link in ModuleCollectionLink.query.filter_by(collection_id=rid).limit(8).all():
                module = LearningModule.query.filter_by(id=link.module_id, user_id=owner_id).first()
                if module:
                    add("module_resource", "module", module.id, reason="Collection is linked to this Module.")

    elif kind == "document_analysis":
        analysis = DocumentAIAnalysis.query.filter_by(id=rid, user_id=owner_id).first()
        if analysis:
            add("analysis_of", "document", analysis.document_id, reason="Saved analysis belongs to this document.")

    return result


def _suggestion_provenance(*, owner_id: int, resource: ContextResource) -> list[ContextConnection]:
    """Expose existing user-approved Note/Document task suggestion lineage."""

    result: list[ContextConnection] = []
    if resource.resource_type == "task":
        for suggestion in DocumentTaskSuggestion.query.filter_by(
            user_id=owner_id, created_task_id=resource.resource_id
        ).limit(20).all():
            item = _connection(
                owner_id=owner_id, relation_type="derived_from", resource_type="document", resource_id=suggestion.document_id,
                outgoing=True, reason=suggestion.description or suggestion.title,
                provenance_type="document_task_suggestion", provenance_id=suggestion.id,
            )
            if item:
                result.append(item)
        note_suggestions = (
            AITaskSuggestion.query.join(Note, Note.id == AITaskSuggestion.note_id)
            .filter(AITaskSuggestion.created_task_id == resource.resource_id, Note.user_id == owner_id)
            .limit(20).all()
        )
        for suggestion in note_suggestions:
            item = _connection(
                owner_id=owner_id, relation_type="derived_from", resource_type="note", resource_id=suggestion.note_id,
                outgoing=True, reason=suggestion.description or suggestion.title,
                provenance_type="note_task_suggestion", provenance_id=suggestion.id,
            )
            if item:
                result.append(item)

    elif resource.resource_type == "document":
        suggestions = DocumentTaskSuggestion.query.filter(
            DocumentTaskSuggestion.user_id == owner_id,
            DocumentTaskSuggestion.document_id == resource.resource_id,
            DocumentTaskSuggestion.created_task_id.isnot(None),
        ).limit(30).all()
        for suggestion in suggestions:
            item = _connection(
                owner_id=owner_id, relation_type="derived_from", resource_type="task", resource_id=int(suggestion.created_task_id),
                outgoing=False, reason=suggestion.description or suggestion.title,
                provenance_type="document_task_suggestion", provenance_id=suggestion.id,
            )
            if item:
                result.append(item)

    elif resource.resource_type == "note":
        suggestions = (
            AITaskSuggestion.query.join(Note, Note.id == AITaskSuggestion.note_id)
            .filter(
                AITaskSuggestion.note_id == resource.resource_id,
                AITaskSuggestion.created_task_id.isnot(None),
                Note.user_id == owner_id,
            ).limit(30).all()
        )
        for suggestion in suggestions:
            item = _connection(
                owner_id=owner_id, relation_type="derived_from", resource_type="task", resource_id=int(suggestion.created_task_id),
                outgoing=False, reason=suggestion.description or suggestion.title,
                provenance_type="note_task_suggestion", provenance_id=suggestion.id,
            )
            if item:
                result.append(item)
    return result


def _legacy_action_provenance(*, owner_id: int, resource: ContextResource) -> list[ContextConnection]:
    """Expose I9 provenance created before I13 without mutating state."""

    result: list[ContextConnection] = []
    if resource.resource_type in {"task", "note", "document_analysis"}:
        proposals = LifeOSActionProposal.query.filter_by(
            user_id=owner_id, status="confirmed",
            execution_resource_type=resource.resource_type,
            execution_resource_id=resource.resource_id,
        ).order_by(LifeOSActionProposal.id.desc()).limit(10).all()
        for proposal in proposals:
            if resource.resource_type == "document_analysis":
                document_id = proposal.payload.get("document_id")
                if document_id:
                    item = _connection(
                        owner_id=owner_id, relation_type="analysis_of", resource_type="document", resource_id=int(document_id),
                        outgoing=True, reason=proposal.reason, provenance_type="ask_lifeos", provenance_id=proposal.id,
                        evidence=proposal.evidence,
                    )
                    if item:
                        result.append(item)
                continue
            for evidence in proposal.evidence:
                if not isinstance(evidence, dict):
                    continue
                source_type = str(evidence.get("source_type") or "").casefold()
                source_id = evidence.get("source_id")
                if source_type == "project" or source_type not in SUPPORTED_RESOURCE_TYPES or source_id is None:
                    continue
                item = _connection(
                    owner_id=owner_id, relation_type="derived_from", resource_type=source_type, resource_id=int(source_id),
                    outgoing=True, reason=proposal.reason, provenance_type="ask_lifeos", provenance_id=proposal.id,
                    evidence=[evidence],
                )
                if item:
                    result.append(item)

    if resource.resource_type in SUPPORTED_RESOURCE_TYPES:
        proposals = LifeOSActionProposal.query.filter_by(user_id=owner_id, status="confirmed").order_by(LifeOSActionProposal.id.desc()).limit(200).all()
        for proposal in proposals:
            exec_type = str(proposal.execution_resource_type or "")
            exec_id = proposal.execution_resource_id
            if exec_type not in {"task", "note"} or exec_id is None:
                continue
            for evidence in proposal.evidence:
                if not isinstance(evidence, dict):
                    continue
                if str(evidence.get("source_type") or "").casefold() != resource.resource_type:
                    continue
                try:
                    same = int(evidence.get("source_id")) == resource.resource_id
                except (TypeError, ValueError):
                    same = False
                if not same:
                    continue
                item = _connection(
                    owner_id=owner_id, relation_type="derived_from", resource_type=exec_type, resource_id=int(exec_id),
                    outgoing=False, reason=proposal.reason, provenance_type="ask_lifeos", provenance_id=proposal.id,
                    evidence=[evidence],
                )
                if item:
                    result.append(item)
    return result


def build_owned_context_connections(*, owner_id: int, resource_type: str, resource_id: int) -> ContextConnectionsResult:
    resource = require_owned_context_resource(owner_id=owner_id, resource_type=resource_type, resource_id=resource_id)
    raw = (
        _persisted_connections(owner_id=owner_id, resource_type=resource.resource_type, resource_id=resource.resource_id)
        + _legacy_action_provenance(owner_id=owner_id, resource=resource)
        + _suggestion_provenance(owner_id=owner_id, resource=resource)
        + _structural_connections(owner_id=owner_id, resource=resource)
    )

    # De-duplicate a relationship surfaced both from a persisted I13 edge and
    # the compatibility view of an older confirmed I9 proposal. Persisted wins.
    raw.sort(key=lambda item: (not item.persisted, item.resource.resource_type, item.resource.label.casefold()))
    seen: set[tuple[str, str, int]] = set()
    result: list[ContextConnection] = []
    for item in raw:
        key = (item.relation_type, item.resource.resource_type, item.resource.resource_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    result.sort(key=lambda item: (
        0 if item.relation_type == "derived_from" else 1 if item.relation_type in {"belongs_to_project", "analysis_of"} else 2,
        item.resource.resource_type,
        item.resource.label.casefold(),
    ))
    limited = len(result) > MAX_CONNECTIONS
    result = result[:MAX_CONNECTIONS]

    if result:
        summary = f"{resource.label} has {len(result)} verified connected context item{'s' if len(result) != 1 else ''}."
        derived = sum(1 for item in result if item.relation_type == "derived_from")
        if derived:
            summary += f" {derived} connection{'s' if derived != 1 else ''} preserve source provenance."
    else:
        summary = f"I did not find a verified LifeOS connection for {resource.label}."
    return ContextConnectionsResult(resource=resource, summary=summary, connections=tuple(result), context_limited=limited)


def _candidate_resources(*, owner_id: int, type_hint: str | None = None) -> list[ContextResource]:
    kinds = [type_hint] if type_hint in SUPPORTED_RESOURCE_TYPES else [
        "task", "document", "note", "project", "module", "lecture", "collection"
    ]
    result: list[ContextResource] = []
    for kind in kinds:
        if kind == "task":
            rows = Task.query.filter_by(user_id=owner_id).order_by(Task.id.desc()).limit(80).all()
        elif kind == "document":
            rows = Document.query.filter_by(user_id=owner_id, is_current_version=True).order_by(Document.id.desc()).limit(80).all()
        elif kind == "note":
            rows = Note.query.filter_by(user_id=owner_id).order_by(Note.id.desc()).limit(80).all()
        elif kind == "project":
            rows = Project.query.filter_by(user_id=owner_id).order_by(Project.id.desc()).limit(60).all()
        elif kind == "module":
            rows = LearningModule.query.filter_by(user_id=owner_id).order_by(LearningModule.id.desc()).limit(60).all()
        elif kind == "lecture":
            rows = (
                Lecture.query.join(LearningModule, LearningModule.id == Lecture.module_id)
                .filter(LearningModule.user_id == owner_id).order_by(Lecture.id.desc()).limit(80).all()
            )
        elif kind == "collection":
            rows = DocumentCollection.query.filter_by(user_id=owner_id).order_by(DocumentCollection.id.desc()).limit(60).all()
        else:
            rows = []
        for row in rows:
            try:
                result.append(require_owned_context_resource(owner_id=owner_id, resource_type=kind, resource_id=row.id))
            except ContextConnectionError:
                continue
    return result


def _type_hint(text: str) -> str | None:
    # Relationship questions often name both the requested result type and the
    # object being traced. Resolve the traced object, not the result noun.
    if any(phrase in text for phrase in (
        "which document is this task based on", "which document is the task based on",
        "which document is task", "which file is task", "task based on",
        "where did this task come from", "where did the task come from",
        "why does this task exist", "why does the task exist", "source of this task",
    )):
        return "task"
    if any(phrase in text for phrase in ("tasks came from", "tasks come from", "tasks created from")):
        return "document"
    if "lecture" in text and any(phrase in text for phrase in ("notes related to", "documents related to", "tasks related to", "connected to")):
        return "lecture"
    if "module" in text and any(phrase in text for phrase in ("notes related to", "documents related to", "tasks related to", "connected to")):
        return "module"

    # Prefer singular object words over "project" as a scope word.
    for pattern, kind in (
        (r"\btask(?:s)?\b", "task"),
        (r"\b(?:document|pdf|file)(?:s)?\b", "document"),
        (r"\bnote(?:s)?\b", "note"),
        (r"\blecture(?:s)?\b", "lecture"),
        (r"\bmodule(?:s)?\b", "module"),
        (r"\bcollection(?:s)?\b", "collection"),
        (r"\bproject(?:s)?\b", "project"),
    ):
        if re.search(pattern, text):
            return kind
    return None


def _explicit_id(text: str, kind: str | None) -> tuple[str, int] | None:
    aliases = {
        "task": r"task\s*#?(\d+)",
        "document": r"(?:document|pdf|file)\s*#?(\d+)",
        "note": r"note\s*#?(\d+)",
        "project": r"project\s*#?(\d+)",
        "module": r"module\s*#?(\d+)",
        "lecture": r"lecture\s*#?(\d+)",
        "collection": r"collection\s*#?(\d+)",
    }
    search_kinds = [kind] if kind in aliases else list(aliases)
    for candidate in search_kinds:
        match = re.search(aliases[candidate], text)
        if match:
            return candidate, int(match.group(1))
    return None


def resolve_owned_context_target(*, owner_id: int, query: str) -> tuple[ContextResource | None, tuple[ContextResource, ...]]:
    text = _normalize(query)
    hint = _type_hint(text)
    explicit = _explicit_id(text, hint)
    if explicit:
        try:
            return require_owned_context_resource(owner_id=owner_id, resource_type=explicit[0], resource_id=explicit[1]), ()
        except ContextConnectionError:
            return None, ()

    resources = _candidate_resources(owner_id=owner_id, type_hint=hint)
    if resources and any(phrase in text for phrase in (
        "latest task", "newest task", "most recent task",
        "latest document", "newest document", "most recent document",
        "latest note", "newest note", "most recent note",
    )):
        return resources[0], ()
    quoted = re.findall(r"['\"]([^'\"]{2,200})['\"]", str(query or ""))
    quoted_norm = [_normalize(item) for item in quoted]
    scored: list[tuple[float, ContextResource]] = []
    for resource in resources:
        label = _normalize(resource.label)
        if not label:
            continue
        score = 0.0
        if label in text:
            score = 1.0
        elif any(q and (q == label or q in label or label in q) for q in quoted_norm):
            score = 0.98
        else:
            label_tokens = set(label.split())
            query_tokens = set(text.split())
            coverage = len(label_tokens & query_tokens) / max(1, len(label_tokens))
            similarity = SequenceMatcher(None, label, text).ratio()
            score = max(coverage * 0.92, similarity * 0.72)
        if score >= 0.62:
            scored.append((score, resource))
    scored.sort(key=lambda item: (-item[0], item[1].label.casefold(), item[1].resource_id))
    if not scored:
        # For pronouns such as "this task", give safe owned candidates rather
        # than guessing which object the user meant.
        pronoun = any(phrase in text for phrase in ("this task", "this document", "this note", "this module", "this lecture", "this project"))
        if pronoun:
            return None, tuple(resources[:MAX_RESOLUTION_CANDIDATES])
        return None, ()
    top_score = scored[0][0]
    near = [resource for score, resource in scored if top_score - score < 0.07][:MAX_RESOLUTION_CANDIDATES]
    if len(near) > 1 and top_score < 0.95:
        return None, tuple(near)
    return scored[0][1], ()


def query_owned_context_connections(*, owner_id: int, query: str) -> ContextConnectionsResult:
    target, candidates = resolve_owned_context_target(owner_id=owner_id, query=query)
    if target is None:
        if candidates:
            kind = candidates[0].resource_type
            label = kind.replace("_", " ")
            return ContextConnectionsResult(
                resource=None,
                summary=f"Which {label} do you mean? Choose one so I can trace its verified LifeOS connections.",
                connections=(), candidates=candidates,
            )
        return ContextConnectionsResult(
            resource=None,
            summary="Name the task, document, note, project, Module, Lecture, or Collection you want me to trace, or specify its LifeOS ID.",
            connections=(), candidates=(),
        )

    result = build_owned_context_connections(
        owner_id=owner_id, resource_type=target.resource_type, resource_id=target.resource_id,
    )

    # Optional result-type filter for natural questions such as
    # "Which tasks came from Architecture.pdf?".
    text = _normalize(query)
    desired: str | None = None
    for plural, kind in (("tasks", "task"), ("documents", "document"), ("notes", "note"), ("lectures", "lecture"), ("modules", "module"), ("collections", "collection")):
        if plural in text and kind != target.resource_type:
            desired = kind
            break
    if desired:
        filtered = tuple(item for item in result.connections if item.resource.resource_type == desired)
        if filtered:
            return ContextConnectionsResult(
                resource=result.resource,
                summary=f"I found {len(filtered)} verified {desired} connection{'s' if len(filtered) != 1 else ''} for {target.label}.",
                connections=filtered,
                context_limited=result.context_limited,
            )
        return ContextConnectionsResult(
            resource=result.resource,
            summary=f"I did not find a verified {desired} connected to {target.label}.",
            connections=(),
            context_limited=result.context_limited,
        )
    return result

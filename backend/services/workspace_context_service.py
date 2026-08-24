"""Shared workspace context for LifeOS intelligence features."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
from typing import Any

from models import (
    Document,
    DocumentAIAnalysis,
    Note,
    Project,
    Task,
)
from services.document_analysis_service import (
    DOCUMENT_ANALYSIS_SCHEMA_VERSION,
)
from services.document_version_service import (
    current_document_filter,
)


MAX_PROJECT_CONTEXT_TASKS = 150
TASK_DESCRIPTION_PREVIEW = 280

MAX_RELATED_PROJECT_NOTES = 10
RELATED_NOTE_PREVIEW = 360

MAX_PROJECT_DOCUMENTS = 10
DOCUMENT_SUMMARY_PREVIEW = 500
DOCUMENT_TEXT_PREVIEW = 700
DOCUMENT_PURPOSE_PREVIEW = 420
DOCUMENT_FINDING_TEXT_PREVIEW = 420
DOCUMENT_FINDING_DETAIL_PREVIEW = 520
DOCUMENT_SOURCE_EVIDENCE_PREVIEW = 280

MAX_DOCUMENT_KEY_POINTS = 5
MAX_DOCUMENT_REQUIREMENTS = 6
MAX_DOCUMENT_DECISIONS = 5
MAX_DOCUMENT_RISKS = 5
MAX_DOCUMENT_DEADLINES = 5
MAX_DOCUMENT_ACTION_ITEMS = 6
MAX_DOCUMENT_MISSING_INFORMATION = 4


class WorkspaceContextNotFoundError(LookupError):
    """Raised when requested workspace information is unavailable."""


def iso_date(value: Any) -> str | None:
    """Convert a date or datetime into ISO-formatted text."""

    if value is None:
        return None

    return value.isoformat()


def compact_text(
    value: Any,
    limit: int = 1000,
) -> str:
    """Clean unnecessary whitespace and limit long text."""

    cleaned = " ".join(str(value or "").split())

    if len(cleaned) <= limit:
        return cleaned

    return cleaned[: limit - 1].rstrip() + "…"


def require_owned_project(
    owner_id: int,
    project_id: int,
) -> Project:
    """Return a project only when it belongs to the requested user."""

    project = Project.query.filter_by(
        id=project_id,
        user_id=owner_id,
    ).first()

    if project is None:
        raise WorkspaceContextNotFoundError(
            "The requested project was not found."
        )

    return project


def build_project_tasks_context(
    owner_id: int,
    project_id: int,
) -> dict[str, Any]:
    """Build an organised summary of tasks linked to a project."""

    all_tasks = Task.query.filter_by(
        user_id=owner_id,
        project_id=project_id,
    ).all()

    status_rank = {
        "Blocked": 0,
        "In Progress": 1,
        "Pending": 2,
        "Completed": 3,
    }

    def task_sort_key(task: Task) -> tuple[Any, ...]:
        return (
            status_rank.get(task.status or "", 2),
            task.deadline is None,
            task.deadline or datetime.max.date(),
            -(task.priority_score or 0),
            task.id,
        )

    selected_tasks = sorted(
        all_tasks,
        key=task_sort_key,
    )[:MAX_PROJECT_CONTEXT_TASKS]

    status_summary = Counter(
        (task.status or "Unknown").strip() or "Unknown"
        for task in all_tasks
    )

    tasks_context: list[dict[str, Any]] = []

    for task in selected_tasks:
        tasks_context.append(
            {
                "id": task.id,
                "title": task.title,
                "description": compact_text(
                    task.description,
                    TASK_DESCRIPTION_PREVIEW,
                ),
                "module": task.module or "",
                "status": task.status or "Pending",
                "priority": task.importance or "Medium",
                "difficulty": task.difficulty or "Medium",
                "deadline": iso_date(task.deadline),
                "completed_at": iso_date(task.completed_at),
                "priority_score": task.priority_score or 0,
            }
        )

    tasks_were_limited = len(all_tasks) > len(tasks_context)

    return {
        "task_status_summary": dict(status_summary),
        "tasks": tasks_context,
        "context_counts": {
            "total_project_tasks": len(all_tasks),
            "tasks_considered": len(tasks_context),
            "tasks_limited": tasks_were_limited,
            "context_limited": tasks_were_limited,
        },
    }


def build_related_notes_context(
    owner_id: int,
    project_id: int,
    exclude_note_id: int | None = None,
) -> list[dict[str, Any]]:
    """Build context from recent notes linked to the same project."""

    query = Note.query.filter_by(
        user_id=owner_id,
        project_id=project_id,
    )

    if exclude_note_id is not None:
        query = query.filter(
            Note.id != exclude_note_id
        )

    related_notes = (
        query
        .order_by(Note.updated_at.desc())
        .limit(MAX_RELATED_PROJECT_NOTES)
        .all()
    )

    notes_context: list[dict[str, Any]] = []

    for note in related_notes:
        latest_completed_analysis = next(
            (
                analysis
                for analysis in note.analyses
                if analysis.status == "Completed"
            ),
            None,
        )

        summary = note.content

        if latest_completed_analysis is not None:
            summary = (
                latest_completed_analysis.insights.get("overview")
                or latest_completed_analysis.summary
                or note.content
            )

        notes_context.append(
            {
                "id": note.id,
                "title": note.title,
                "note_type": note.note_type or "Quick Note",
                "summary": compact_text(
                    summary,
                    RELATED_NOTE_PREVIEW,
                ),
                "is_pinned": bool(note.is_pinned),
                "created_at": iso_date(note.created_at),
                "updated_at": iso_date(note.updated_at),
            }
        )

    return notes_context


def _clean_document_source(
    value: Any,
) -> dict[str, Any]:
    """Return compact page-level provenance for project document findings."""

    source = (
        value
        if isinstance(value, dict)
        else {}
    )

    raw_page = source.get("page")

    try:
        page = int(raw_page)
    except (TypeError, ValueError):
        page = None

    if page is not None and page <= 0:
        page = None

    return {
        "page": page,
        "section": compact_text(
            source.get("section"),
            160,
        ),
        "evidence": compact_text(
            source.get("evidence"),
            DOCUMENT_SOURCE_EVIDENCE_PREVIEW,
        ),
    }


def _compact_structured_findings(
    items: Any,
    *,
    text_keys: tuple[str, ...],
    detail_keys: tuple[str, ...],
    limit: int,
) -> list[dict[str, Any]]:
    """Convert one structured analysis section into bounded shared context."""

    if not isinstance(items, list):
        return []

    results: list[dict[str, Any]] = []

    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue

        text_value = next(
            (
                raw_item.get(key)
                for key in text_keys
                if raw_item.get(key) not in (
                    None,
                    "",
                )
            ),
            "",
        )

        detail_value = next(
            (
                raw_item.get(key)
                for key in detail_keys
                if raw_item.get(key) not in (
                    None,
                    "",
                )
            ),
            "",
        )

        text = compact_text(
            text_value,
            DOCUMENT_FINDING_TEXT_PREVIEW,
        )

        detail = compact_text(
            detail_value,
            DOCUMENT_FINDING_DETAIL_PREVIEW,
        )

        if not text and not detail:
            continue

        results.append(
            {
                "text": text,
                "detail": detail,
                "source": _clean_document_source(
                    raw_item.get("source")
                ),
            }
        )

        if len(results) >= limit:
            break

    return results


def _compact_document_deadlines(
    items: Any,
) -> list[dict[str, Any]]:
    """Return bounded document deadlines with provenance."""

    if not isinstance(items, list):
        return []

    results: list[dict[str, Any]] = []

    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue

        description = compact_text(
            raw_item.get("description"),
            DOCUMENT_FINDING_DETAIL_PREVIEW,
        )

        date_value = compact_text(
            raw_item.get("date"),
            20,
        )

        if not description and not date_value:
            continue

        results.append(
            {
                "date": date_value or None,
                "description": description,
                "source": _clean_document_source(
                    raw_item.get("source")
                ),
            }
        )

        if len(results) >= MAX_DOCUMENT_DEADLINES:
            break

    return results


def _compact_document_actions(
    items: Any,
) -> list[dict[str, Any]]:
    """Return reviewable document actions without creating or changing tasks."""

    if not isinstance(items, list):
        return []

    results: list[dict[str, Any]] = []

    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue

        title = compact_text(
            raw_item.get("title"),
            DOCUMENT_FINDING_TEXT_PREVIEW,
        )

        description = compact_text(
            raw_item.get("description"),
            DOCUMENT_FINDING_DETAIL_PREVIEW,
        )

        if not title and not description:
            continue

        raw_tags = raw_item.get("tags")
        tags: list[str] = []

        if isinstance(raw_tags, list):
            for raw_tag in raw_tags:
                tag = compact_text(
                    raw_tag,
                    40,
                )

                if tag:
                    tags.append(tag)

                if len(tags) >= 6:
                    break

        results.append(
            {
                "title": title,
                "description": description,
                "priority": compact_text(
                    raw_item.get("priority"),
                    20,
                )
                or "Medium",
                "deadline": (
                    compact_text(
                        raw_item.get("deadline"),
                        20,
                    )
                    or None
                ),
                "tags": tags,
                "source": _clean_document_source(
                    raw_item.get("source")
                ),
            }
        )

        if len(results) >= MAX_DOCUMENT_ACTION_ITEMS:
            break

    return results


def _analysis_expected_fingerprints(
    document: Document,
    analysis: DocumentAIAnalysis,
) -> set[str]:
    """
    Return fingerprints that mean a completed analysis still matches the PDF.

    Step 6 fingerprints include schema version and the user-confirmed type.
    The legacy plain-text fingerprint remains accepted so older unchanged
    analyses stay usable after the fingerprint format evolved.
    """

    extracted_text = str(
        document.extracted_text or ""
    ).strip()

    if not extracted_text:
        return set()

    legacy_fingerprint = hashlib.sha256(
        extracted_text.encode(
            "utf-8"
        )
    ).hexdigest()

    insights = analysis.insights
    raw_type_metadata = insights.get(
        "type_metadata"
    )

    type_metadata = (
        raw_type_metadata
        if isinstance(
            raw_type_metadata,
            dict,
        )
        else {}
    )

    confirmed_type_key = compact_text(
        type_metadata.get(
            "confirmed_type_key"
        ),
        80,
    )

    type_identity = (
        confirmed_type_key
        or "legacy_unconfirmed"
    )

    modern_input = (
        f"{DOCUMENT_ANALYSIS_SCHEMA_VERSION}\n"
        f"{type_identity}\n"
        f"{extracted_text}"
    )

    modern_fingerprint = hashlib.sha256(
        modern_input.encode(
            "utf-8"
        )
    ).hexdigest()

    return {
        legacy_fingerprint,
        modern_fingerprint,
    }


def _analysis_is_current(
    document: Document,
    analysis: DocumentAIAnalysis,
) -> bool:
    """Return True only when saved findings match the document's current text."""

    fingerprint = str(
        analysis.source_fingerprint or ""
    ).strip()

    if not fingerprint:
        return False

    return fingerprint in _analysis_expected_fingerprints(
        document,
        analysis,
    )


def _trusted_document_analysis_context(
    analysis: DocumentAIAnalysis,
) -> dict[str, Any]:
    """Build bounded, page-aware structured facts from one current analysis."""

    insights = analysis.insights

    key_points = _compact_structured_findings(
        insights.get("key_points"),
        text_keys=(
            "title",
            "text",
        ),
        detail_keys=(
            "detail",
            "details",
        ),
        limit=MAX_DOCUMENT_KEY_POINTS,
    )

    requirements = _compact_structured_findings(
        insights.get("requirements"),
        text_keys=(
            "requirement",
            "title",
            "text",
        ),
        detail_keys=(
            "details",
            "detail",
        ),
        limit=MAX_DOCUMENT_REQUIREMENTS,
    )

    decisions = _compact_structured_findings(
        insights.get("decisions"),
        text_keys=(
            "decision",
            "title",
            "text",
        ),
        detail_keys=(
            "reason",
            "detail",
        ),
        limit=MAX_DOCUMENT_DECISIONS,
    )

    risks = _compact_structured_findings(
        insights.get("risks"),
        text_keys=(
            "risk",
            "title",
            "text",
        ),
        detail_keys=(
            "impact",
            "detail",
        ),
        limit=MAX_DOCUMENT_RISKS,
    )

    missing_information = _compact_structured_findings(
        insights.get(
            "missing_information"
        ),
        text_keys=(
            "question",
            "title",
            "text",
        ),
        detail_keys=(
            "why_it_matters",
            "detail",
        ),
        limit=MAX_DOCUMENT_MISSING_INFORMATION,
    )

    deadlines = _compact_document_deadlines(
        insights.get("deadlines")
    )

    action_items = _compact_document_actions(
        insights.get("action_items")
    )

    finding_count = sum(
        len(items)
        for items in (
            key_points,
            requirements,
            decisions,
            risks,
            deadlines,
            action_items,
            missing_information,
        )
    )

    return {
        "analysis_id": analysis.id,
        "document_type": (
            compact_text(
                insights.get(
                    "document_type"
                ),
                80,
            )
            or compact_text(
                analysis.document_type,
                80,
            )
        ),
        "summary": compact_text(
            insights.get("summary")
            or analysis.summary,
            DOCUMENT_SUMMARY_PREVIEW,
        ),
        "purpose": compact_text(
            insights.get("purpose"),
            DOCUMENT_PURPOSE_PREVIEW,
        ),
        "key_points": key_points,
        "requirements": requirements,
        "decisions": decisions,
        "risks": risks,
        "deadlines": deadlines,
        "action_items": action_items,
        "missing_information": missing_information,
        "finding_count": finding_count,
        "analysed_at": iso_date(
            analysis.created_at
        ),
    }


def build_project_documents_context(
    *,
    owner_id: int,
    project_id: int,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
]:
    """
    Build ownership-safe current document intelligence for one project.

    Only completed analyses owned by the project owner are considered. Stale
    analyses remain visible through status metadata but their structured facts
    are not exposed as trusted current findings.
    """

    project = require_owned_project(
        owner_id=owner_id,
        project_id=project_id,
    )

    base_query = (
        Document.query
        .join(
            Project,
            Document.project_id == Project.id,
        )
        .filter(
            Document.project_id == project.id,
            Project.user_id == owner_id,
            current_document_filter(),
        )
    )

    total_documents = base_query.count()

    documents = (
        base_query
        .order_by(
            Document.uploaded_at.desc(),
            Document.id.desc(),
        )
        .limit(MAX_PROJECT_DOCUMENTS)
        .all()
    )

    document_ids = [
        document.id
        for document in documents
    ]

    analyses_by_document: dict[
        int,
        list[DocumentAIAnalysis],
    ] = {
        document_id: []
        for document_id in document_ids
    }

    if document_ids:
        analyses = (
            DocumentAIAnalysis.query
            .filter(
                DocumentAIAnalysis.document_id.in_(
                    document_ids
                ),
                DocumentAIAnalysis.user_id == owner_id,
                DocumentAIAnalysis.status == "Completed",
            )
            .order_by(
                DocumentAIAnalysis.created_at.desc(),
                DocumentAIAnalysis.id.desc(),
            )
            .all()
        )

        for analysis in analyses:
            analyses_by_document.setdefault(
                analysis.document_id,
                [],
            ).append(
                analysis
            )

    documents_context: list[
        dict[str, Any]
    ] = []

    current_count = 0
    stale_count = 0
    no_analysis_count = 0
    finding_count = 0

    for document in documents:
        completed_analyses = (
            analyses_by_document.get(
                document.id,
                [],
            )
        )

        current_analysis = next(
            (
                analysis
                for analysis in completed_analyses
                if _analysis_is_current(
                    document,
                    analysis,
                )
            ),
            None,
        )

        if current_analysis is not None:
            analysis_status = "Current"
            current_count += 1
            trusted_analysis = (
                _trusted_document_analysis_context(
                    current_analysis
                )
            )
            finding_count += int(
                trusted_analysis.get(
                    "finding_count",
                    0,
                )
                or 0
            )

        elif completed_analyses:
            analysis_status = "Stale"
            stale_count += 1
            trusted_analysis = None

        else:
            analysis_status = "Not analysed"
            no_analysis_count += 1
            trusted_analysis = None

        documents_context.append(
            {
                "id": document.id,
                "filename": document.filename,
                "version_family_id": document.version_family_id,
                "version_number": document.version_number,
                "is_current_version": bool(document.is_current_version),

                # Backwards-compatible preview fields.
                "summary": compact_text(
                    document.summary,
                    DOCUMENT_SUMMARY_PREVIEW,
                ),
                "text_preview": compact_text(
                    document.extracted_text,
                    DOCUMENT_TEXT_PREVIEW,
                ),
                "detected_modules": compact_text(
                    document.detected_modules,
                    300,
                ),
                "extracted_tasks": compact_text(
                    document.extracted_tasks,
                    400,
                ),

                # Step 10 trusted structured project knowledge.
                "analysis_status": analysis_status,
                "has_current_analysis": (
                    current_analysis
                    is not None
                ),
                "trusted_analysis": trusted_analysis,
                "uploaded_at": iso_date(
                    document.uploaded_at
                ),
                "has_extracted_text": bool(
                    document.extracted_text
                ),
            }
        )

    documents_limited = (
        total_documents
        > len(
            documents_context
        )
    )

    return (
        documents_context,
        {
            "total_project_documents": total_documents,
            "documents_considered": len(
                documents_context
            ),
            "documents_limited": documents_limited,
            "documents_with_current_analysis": current_count,
            "documents_with_stale_analysis": stale_count,
            "documents_without_analysis": no_analysis_count,
            "document_findings_considered": finding_count,
        },
    )

def build_project_context(
    owner_id: int,
    project_id: int,
    exclude_note_id: int | None = None,
) -> dict[str, Any]:
    """Build shared project context for LifeOS intelligence features."""

    project = require_owned_project(
        owner_id=owner_id,
        project_id=project_id,
    )

    task_context = build_project_tasks_context(
        owner_id=owner_id,
        project_id=project.id,
    )

    related_notes_context = build_related_notes_context(
        owner_id=owner_id,
        project_id=project.id,
        exclude_note_id=exclude_note_id,
    )

    (
        documents_context,
        document_context_counts,
    ) = build_project_documents_context(
        owner_id=owner_id,
        project_id=project.id,
    )

    return {
        "project": {
            "id": project.id,
            "title": project.title,
            "description": compact_text(project.description),
            "goal": compact_text(project.goal),
            "project_type": project.project_type or "",
            "tech_stack": project.tech_stack or "",
            "status": project.status or "",
            "priority": project.priority or "",
            "current_phase": project.current_phase or "",
            "progress": project.progress or 0,
            "start_date": iso_date(project.start_date),
            "deadline": iso_date(project.deadline),
            "created_at": iso_date(project.created_at),
            "updated_at": iso_date(project.updated_at),
        },
        "task_status_summary": task_context[
            "task_status_summary"
        ],
        "tasks": task_context["tasks"],
        "recent_related_notes": related_notes_context,
        "documents": documents_context,
        "context_counts": {
            **task_context["context_counts"],
            "related_notes_considered": len(
                related_notes_context
            ),
            **document_context_counts,
            "context_limited": bool(
                task_context["context_counts"].get(
                    "context_limited",
                    False,
                )
                or document_context_counts.get(
                    "documents_limited",
                    False,
                )
            ),
        },
    }
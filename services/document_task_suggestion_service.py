"""Build task suggestions from Document Brain analysis results."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from models import (
    Document,
    DocumentAIAnalysis,
    DocumentTaskSuggestion,
    Task,
)
from services.task_duplicate_service import (
    DUPLICATE_OVERALL_THRESHOLD,
    assess_task_duplicate,
    title_similarity_score,
)



# Backward-compatible public constant used by the existing Step 9 tests and
# callers. Step 11 now owns the threshold in task_duplicate_service.
MATCH_THRESHOLD = DUPLICATE_OVERALL_THRESHOLD


SUPPORTED_PRIORITIES = {
    "Low",
    "Medium",
    "High",
}


class DocumentSuggestionBuildError(RuntimeError):
    """Raised when suggestions cannot be built safely."""


def build_document_task_suggestions(
    *,
    analysis: DocumentAIAnalysis,
    document: Document,
    user_id: int,
) -> list[DocumentTaskSuggestion]:
    """Convert analysed action items into pending suggestions."""

    if analysis.document_id != document.id:
        raise DocumentSuggestionBuildError(
            "The analysis does not belong to this document."
        )

    if analysis.user_id != user_id:
        raise DocumentSuggestionBuildError(
            "The analysis does not belong to this user."
        )

    insights = analysis.insights
    action_items = insights.get(
        "action_items",
        [],
    )

    if not isinstance(action_items, list):
        return []

    existing_tasks = Task.query.filter_by(
        user_id=user_id,
        project_id=document.project_id,
    ).all()

    suggestions: list[DocumentTaskSuggestion] = []
    seen_titles: set[str] = set()

    for action in action_items:
        if not isinstance(action, dict):
            continue

        title = _clean_text(
            action.get("title"),
            limit=255,
        )

        if not title:
            continue

        normalised_title = _normalise_match_text(title)

        # Prevent duplicate suggestions from one AI response.
        if normalised_title in seen_titles:
            continue

        seen_titles.add(normalised_title)

        description = _clean_text(
            action.get("description"),
            limit=3000,
        )

        priority = _clean_priority(
            action.get("priority")
        )

        deadline = _parse_deadline(
            action.get("deadline")
        )

        duplicate_assessment = assess_task_duplicate(
            suggestion_title=title,
            suggestion_description=description,
            existing_tasks=existing_tasks,
        )

        matched_task = duplicate_assessment.matched_task
        match_score = duplicate_assessment.overall_score

        tags = _clean_tags(
            action.get("tags")
        )

        source = action.get("source")

        if not isinstance(source, dict):
            source = {}

        suggestions.append(
            DocumentTaskSuggestion(
                analysis_id=analysis.id,
                document_id=document.id,
                user_id=user_id,
                title=title,
                description=description,
                tags=tags,
                priority=priority,
                deadline=deadline,
                source_json=json.dumps(
                    source,
                    ensure_ascii=False,
                ),
                status="Pending",
                matched_task_id=(
                    matched_task.id
                    if matched_task is not None
                    else None
                ),
                match_score=round(
                    match_score,
                    4,
                ),
                created_task_id=None,
            )
        )

    return suggestions


def find_best_task_match(
    *,
    suggestion_title: str,
    existing_tasks: list[Task],
) -> tuple[Task | None, float]:
    """Backward-compatible Step 9 title-only duplicate helper."""

    assessment = assess_task_duplicate(
        suggestion_title=suggestion_title,
        suggestion_description=None,
        existing_tasks=existing_tasks,
        use_semantic=False,
    )

    return (
        assessment.matched_task,
        assessment.overall_score,
    )


def calculate_task_match_score(
    first_title: Any,
    second_title: Any,
) -> float:
    """Backward-compatible deterministic title similarity helper."""

    return title_similarity_score(
        first_title,
        second_title,
    )

def _normalise_match_text(
    value: Any,
) -> str:
    """Normalise titles used to deduplicate suggestions generated together."""

    cleaned = str(
        value
        or ""
    ).casefold()

    cleaned = re.sub(
        r"[^\w\s]",
        " ",
        cleaned,
        flags=re.UNICODE,
    )

    return " ".join(
        cleaned.split()
    )


def _clean_tags(value: Any) -> str | None:
    if value in (None, ""):
        return None

    if isinstance(value, str):
        raw_items = value.replace(";", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = [value]

    tags: list[str] = []
    seen: set[str] = set()

    for raw_item in raw_items:
        tag = _clean_text(raw_item, limit=40)
        key = tag.casefold()

        if not tag or key in seen:
            continue

        seen.add(key)
        tags.append(tag)

        if len(tags) >= 6:
            break

    return ", ".join(tags) or None


def _clean_text(
    value: Any,
    *,
    limit: int,
) -> str:
    cleaned = " ".join(
        str(value or "").split()
    )

    return cleaned[:limit]


def _clean_priority(
    value: Any,
) -> str:
    cleaned = str(
        value or ""
    ).strip().title()

    if cleaned in SUPPORTED_PRIORITIES:
        return cleaned

    return "Medium"


def _parse_deadline(
    value: Any,
):
    cleaned = str(
        value or ""
    ).strip()

    if not cleaned:
        return None

    try:
        return datetime.strptime(
            cleaned,
            "%Y-%m-%d",
        ).date()

    except ValueError:
        return None
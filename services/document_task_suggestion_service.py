"""Build task suggestions from Document Brain analysis results."""

from __future__ import annotations

import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

from models import (
    Document,
    DocumentAIAnalysis,
    DocumentTaskSuggestion,
    Task,
)


MATCH_THRESHOLD = 0.72

SUPPORTED_PRIORITIES = {
    "Low",
    "Medium",
    "High",
}

# These words describe actions but usually do not identify
# the actual subject of a task.
MATCH_STOP_WORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "to",
    "for",
    "of",
    "in",
    "on",
    "with",
    "build",
    "create",
    "implement",
    "develop",
    "add",
    "prepare",
    "update",
    "fix",
    "test",
    "complete",
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

        matched_task, match_score = find_best_task_match(
            suggestion_title=title,
            existing_tasks=existing_tasks,
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
    """Return the most similar existing task above the threshold."""

    best_task: Task | None = None
    best_score = 0.0

    for task in existing_tasks:
        score = calculate_task_match_score(
            suggestion_title,
            task.title,
        )

        if score > best_score:
            best_task = task
            best_score = score

    if best_score < MATCH_THRESHOLD:
        return None, best_score

    return best_task, best_score


def calculate_task_match_score(
    first_title: Any,
    second_title: Any,
) -> float:
    """Calculate a deterministic similarity score for two task titles."""

    first = _normalise_match_text(
        first_title
    )

    second = _normalise_match_text(
        second_title
    )

    if not first or not second:
        return 0.0

    if first == second:
        return 1.0

    sequence_score = SequenceMatcher(
        None,
        first,
        second,
    ).ratio()

    first_tokens = _meaningful_tokens(first)
    second_tokens = _meaningful_tokens(second)

    token_score = 0.0

    if first_tokens and second_tokens:
        intersection = (
            first_tokens
            & second_tokens
        )

        smaller_size = min(
            len(first_tokens),
            len(second_tokens),
        )

        token_score = (
            len(intersection)
            / smaller_size
        )

    return max(
        sequence_score,
        token_score,
    )


def _normalise_match_text(
    value: Any,
) -> str:
    """Normalise a title for duplicate comparison."""

    cleaned = str(
        value or ""
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


def _meaningful_tokens(
    value: str,
) -> set[str]:
    """Return useful title tokens without generic action words."""

    return {
        token
        for token in value.split()
        if (
            len(token) > 1
            and token not in MATCH_STOP_WORDS
        )
    }


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
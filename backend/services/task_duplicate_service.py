"""Project-level duplicate-work detection for Document Brain task suggestions.

Step 11 compares a proposed document action with existing project tasks using
title overlap, description overlap, current task status, and optional semantic
similarity. Semantic embeddings improve paraphrase detection when configured,
but the workflow safely falls back to deterministic lexical comparison.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from flask import current_app, has_app_context
from google import genai

from models import Task
from services.document_embedding_service import (
    _generate_embeddings,
    cosine_similarity,
    get_embedding_configuration,
    normalize_vector,
)


DUPLICATE_OVERALL_THRESHOLD = 0.72
STRONG_TITLE_THRESHOLD = 0.82
STRONG_DESCRIPTION_THRESHOLD = 0.90
DESCRIPTION_SUPPORTING_TITLE_THRESHOLD = 0.35
STRONG_SEMANTIC_THRESHOLD = 0.90
CONTINUE_THRESHOLD = 0.82

TITLE_WEIGHT = 0.50
DESCRIPTION_WEIGHT = 0.20
SEMANTIC_WEIGHT = 0.30

ACTIVE_TASK_STATUSES = {
    "Pending",
    "In Progress",
    "Blocked",
}

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


@dataclass(frozen=True)
class TaskDuplicateAssessment:
    """One best-match duplicate decision for proposed project work."""

    matched_task: Task | None
    overall_score: float
    title_score: float
    description_score: float
    semantic_score: float | None
    recommendation: str
    reason: str

    @property
    def is_duplicate(self) -> bool:
        return self.matched_task is not None

    @property
    def recommendation_label(self) -> str:
        return {
            "continue_existing": "Continue existing task",
            "update_existing": "Review and update existing task",
            "create_new": "Create new task",
        }.get(
            self.recommendation,
            "Review existing work",
        )

    @property
    def overlap_label(self) -> str:
        if not self.is_duplicate:
            return "No strong overlap"

        if self.overall_score >= 0.86:
            return "Very strong overlap"

        if self.overall_score >= 0.78:
            return "Strong overlap"

        return "Possible overlap"


def assess_task_duplicate(
    *,
    suggestion_title: str,
    suggestion_description: str | None,
    existing_tasks: list[Task],
    use_semantic: bool = True,
) -> TaskDuplicateAssessment:
    """
    Return the strongest existing-task match and the safest recommendation.

    Every existing task is evaluated independently before LifeOS chooses the
    best match. This prevents a strong title, description, or semantic duplicate
    from being hidden by a different task with a slightly higher blended score.
    """

    if not existing_tasks:
        return _no_duplicate()

    title_scores = [
        title_similarity_score(
            suggestion_title,
            task.title,
        )
        for task in existing_tasks
    ]

    description_scores = [
        text_similarity_score(
            suggestion_description,
            task.description,
        )
        for task in existing_tasks
    ]

    if use_semantic and _semantic_enabled():
        semantic_scores = _semantic_similarity_scores(
            suggestion_title=suggestion_title,
            suggestion_description=suggestion_description,
            existing_tasks=existing_tasks,
        )
    else:
        semantic_scores = [
            None
            for _ in existing_tasks
        ]

    if len(semantic_scores) != len(existing_tasks):
        semantic_scores = [
            None
            for _ in existing_tasks
        ]

    has_description = bool(
        str(
            suggestion_description
            or ""
        ).strip()
    )

    candidates: list[
        tuple[
            int,
            Task,
            float,
            float,
            float | None,
            float,
            bool,
            float,
        ]
    ] = []

    for index, task in enumerate(existing_tasks):
        title_score = title_scores[index]
        description_score = description_scores[index]
        semantic_score = semantic_scores[index]

        overall_score = _combined_score(
            title_score=title_score,
            description_score=description_score,
            semantic_score=semantic_score,
            has_suggestion_description=has_description,
        )

        strong_description_overlap = (
            has_description
            and description_score >= STRONG_DESCRIPTION_THRESHOLD
            and title_score >= DESCRIPTION_SUPPORTING_TITLE_THRESHOLD
        )

        duplicate = (
            overall_score >= DUPLICATE_OVERALL_THRESHOLD
            or title_score >= STRONG_TITLE_THRESHOLD
            or strong_description_overlap
            or (
                semantic_score is not None
                and semantic_score >= STRONG_SEMANTIC_THRESHOLD
            )
        )

        duplicate_strength = _duplicate_strength(
            overall_score=overall_score,
            title_score=title_score,
            description_score=description_score,
            semantic_score=semantic_score,
            strong_description_overlap=strong_description_overlap,
        )

        candidates.append(
            (
                index,
                task,
                title_score,
                description_score,
                semantic_score,
                overall_score,
                duplicate,
                duplicate_strength,
            )
        )

    duplicate_candidates = [
        candidate
        for candidate in candidates
        if candidate[6]
    ]

    if duplicate_candidates:
        best = max(
            duplicate_candidates,
            key=lambda item: (
                item[7],
                item[5],
                item[2],
                item[3],
            ),
        )

        (
            _,
            task,
            title_score,
            description_score,
            semantic_score,
            overall_score,
            _,
            _,
        ) = best

        recommendation, reason = _recommendation_for_task(
            task=task,
            overall_score=overall_score,
            title_score=title_score,
            semantic_score=semantic_score,
        )

        return TaskDuplicateAssessment(
            matched_task=task,
            overall_score=round(
                overall_score,
                4,
            ),
            title_score=round(
                title_score,
                4,
            ),
            description_score=round(
                description_score,
                4,
            ),
            semantic_score=(
                round(
                    semantic_score,
                    4,
                )
                if semantic_score is not None
                else None
            ),
            recommendation=recommendation,
            reason=reason,
        )

    best = max(
        candidates,
        key=lambda item: (
            item[5],
            item[2],
            item[3],
        ),
    )

    (
        _,
        _task,
        title_score,
        description_score,
        semantic_score,
        overall_score,
        _,
        _,
    ) = best

    return TaskDuplicateAssessment(
        matched_task=None,
        overall_score=round(
            overall_score,
            4,
        ),
        title_score=round(
            title_score,
            4,
        ),
        description_score=round(
            description_score,
            4,
        ),
        semantic_score=(
            round(
                semantic_score,
                4,
            )
            if semantic_score is not None
            else None
        ),
        recommendation="create_new",
        reason=(
            "Existing project tasks do not overlap strongly enough "
            "with this document action."
        ),
    )


def _duplicate_strength(
    *,
    overall_score: float,
    title_score: float,
    description_score: float,
    semantic_score: float | None,
    strong_description_overlap: bool,
) -> float:
    """Rank candidates that already crossed at least one duplicate gate."""

    signals = [
        (
            overall_score
            if overall_score >= DUPLICATE_OVERALL_THRESHOLD
            else 0.0
        ),
        (
            title_score
            if title_score >= STRONG_TITLE_THRESHOLD
            else 0.0
        ),
        (
            description_score
            if strong_description_overlap
            else 0.0
        ),
        (
            semantic_score
            if (
                semantic_score is not None
                and semantic_score >= STRONG_SEMANTIC_THRESHOLD
            )
            else 0.0
        ),
    ]

    return max(signals)

def title_similarity_score(
    first_title: Any,
    second_title: Any,
) -> float:
    """Deterministic title overlap used by Step 9 and Step 11."""

    return text_similarity_score(
        first_title,
        second_title,
        remove_action_words=True,
    )


def text_similarity_score(
    first_value: Any,
    second_value: Any,
    *,
    remove_action_words: bool = False,
) -> float:
    """Return deterministic sequence/token similarity for arbitrary task text."""

    first = _normalise_text(
        first_value
    )
    second = _normalise_text(
        second_value
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

    first_tokens = _meaningful_tokens(
        first,
        remove_action_words=remove_action_words,
    )

    second_tokens = _meaningful_tokens(
        second,
        remove_action_words=remove_action_words,
    )

    token_score = 0.0

    if first_tokens and second_tokens:
        intersection = (
            first_tokens
            & second_tokens
        )

        union = (
            first_tokens
            | second_tokens
        )

        containment = (
            len(intersection)
            / min(
                len(first_tokens),
                len(second_tokens),
            )
        )

        jaccard = (
            len(intersection)
            / len(union)
        )

        token_score = max(
            containment,
            jaccard,
        )

    return max(
        sequence_score,
        token_score,
    )


def prepare_task_for_semantic_comparison(
    *,
    title: Any,
    description: Any,
) -> str:
    """Prepare task meaning for embedding-based duplicate comparison."""

    cleaned_title = " ".join(
        str(
            title
            or ""
        ).split()
    ).strip()

    cleaned_description = " ".join(
        str(
            description
            or ""
        ).split()
    ).strip()

    return (
        f"{cleaned_title}\n"
        f"{cleaned_description}"
    ).strip()


def _semantic_similarity_scores(
    *,
    suggestion_title: str,
    suggestion_description: str | None,
    existing_tasks: list[Task],
) -> list[float | None]:
    """
    Compare one proposed task with all project tasks using Gemini embeddings.

    Any provider/configuration failure returns lexical-only fallbacks instead of
    blocking document analysis or task creation.
    """

    try:
        configuration = get_embedding_configuration()

        texts = [
            prepare_task_for_semantic_comparison(
                title=suggestion_title,
                description=suggestion_description,
            ),
            *[
                prepare_task_for_semantic_comparison(
                    title=task.title,
                    description=task.description,
                )
                for task in existing_tasks
            ],
        ]

        client = genai.Client(
            api_key=configuration.api_key
        )

        vectors = _generate_embeddings(
            client=client,
            model=configuration.model,
            dimensions=configuration.dimensions,
            texts=texts,
        )

        if len(vectors) != len(texts):
            return [
                None
                for _ in existing_tasks
            ]

        suggestion_vector = normalize_vector(
            vectors[0]
        )

        return [
            max(
                -1.0,
                min(
                    1.0,
                    cosine_similarity(
                        suggestion_vector,
                        normalize_vector(vector),
                    ),
                ),
            )
            for vector in vectors[1:]
        ]

    except Exception:
        return [
            None
            for _ in existing_tasks
        ]


def _combined_score(
    *,
    title_score: float,
    description_score: float,
    semantic_score: float | None,
    has_suggestion_description: bool,
) -> float:
    """Blend available evidence while keeping scores comparable."""

    components: list[
        tuple[float, float]
    ] = [
        (
            TITLE_WEIGHT,
            title_score,
        ),
    ]

    if has_suggestion_description:
        components.append(
            (
                DESCRIPTION_WEIGHT,
                description_score,
            )
        )

    if semantic_score is not None:
        components.append(
            (
                SEMANTIC_WEIGHT,
                max(
                    0.0,
                    semantic_score,
                ),
            )
        )

    total_weight = sum(
        weight
        for weight, _ in components
    )

    if total_weight <= 0:
        return 0.0

    return sum(
        weight * score
        for weight, score in components
    ) / total_weight


def _recommendation_for_task(
    *,
    task: Task,
    overall_score: float,
    title_score: float,
    semantic_score: float | None,
) -> tuple[str, str]:
    """Use task status and overlap strength to recommend the safest action."""

    strong_overlap = (
        overall_score >= CONTINUE_THRESHOLD
        or title_score >= 0.90
        or (
            semantic_score is not None
            and semantic_score >= 0.88
        )
    )

    status = str(
        task.status
        or "Pending"
    ).strip()

    if (
        status in ACTIVE_TASK_STATUSES
        and strong_overlap
    ):
        return (
            "continue_existing",
            (
                f'This document action appears to describe work already '
                f'tracked by "{task.title}", which is currently {status}.'
            ),
        )

    if status == "Completed":
        return (
            "update_existing",
            (
                f'A very similar task, "{task.title}", is already completed. '
                "Review whether the existing task should be updated or reopened "
                "before creating duplicate work."
            ),
        )

    return (
        "update_existing",
        (
            f'The document action overlaps with "{task.title}". Review the '
            "existing task and update it if the new document adds details."
        ),
    )


def _no_duplicate() -> TaskDuplicateAssessment:
    return TaskDuplicateAssessment(
        matched_task=None,
        overall_score=0.0,
        title_score=0.0,
        description_score=0.0,
        semantic_score=None,
        recommendation="create_new",
        reason=(
            "No existing project task is similar enough to treat as "
            "duplicate work."
        ),
    )


def _semantic_enabled() -> bool:
    """
    Return whether live semantic duplicate comparison may call the provider.

    Flask tests stay deterministic and never consume API quota merely because
    a developer's local .env contains a Gemini key.
    """

    if (
        has_app_context()
        and bool(
            current_app.config.get(
                "TESTING",
                False,
            )
        )
    ):
        return False

    raw_value = os.getenv(
        "TASK_DUPLICATE_SEMANTIC_ENABLED",
        "1",
    ).strip().casefold()

    return raw_value not in {
        "0",
        "false",
        "no",
        "off",
    }


def _normalise_text(
    value: Any,
) -> str:
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


def _meaningful_tokens(
    value: str,
    *,
    remove_action_words: bool,
) -> set[str]:
    return {
        token
        for token in value.split()
        if (
            len(token) > 1
            and (
                not remove_action_words
                or token not in MATCH_STOP_WORDS
            )
        )
    }

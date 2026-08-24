"""Step 13C — semantic alignment hints for two document evidence registries.

Alignment hints are advisory. They help the comparison model pair paraphrased
facts before classification, but they are never shown as factual output and
their similarity scores stay backend-only.

Gemini embeddings improve paraphrase alignment when configured. If embeddings
are disabled/unavailable, LifeOS continues with deterministic lexical hints.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import os
import re
from typing import Any

from flask import current_app, has_app_context
from google import genai

from services.document_comparison_candidate_service import (
    ComparisonEvidence,
    DocumentComparisonCandidateBundle,
)
from services.document_embedding_service import (
    DocumentEmbeddingError,
    _generate_embeddings,
    cosine_similarity,
    get_embedding_configuration,
    normalize_vector,
)


SEMANTIC_ALIGNMENT_THRESHOLD = 0.72
LEXICAL_ALIGNMENT_THRESHOLD = 0.50
MAX_ALIGNMENT_HINTS = 36
MAX_HINTS_PER_SOURCE = 2


@dataclass(frozen=True)
class ComparisonAlignmentHint:
    """One likely semantic relationship between A evidence and B evidence."""

    source_a_id: str
    source_b_id: str
    score: float
    method: str


def align_comparison_candidates(
    bundle: DocumentComparisonCandidateBundle,
    *,
    use_semantic: bool = True,
) -> list[ComparisonAlignmentHint]:
    """Return the strongest likely A/B evidence relationships."""

    if (
        not bundle.evidence_a
        or not bundle.evidence_b
    ):
        return []

    lexical_scores = _lexical_pair_scores(
        bundle.evidence_a,
        bundle.evidence_b,
    )

    semantic_scores: dict[
        tuple[str, str],
        float,
    ] = {}

    if (
        use_semantic
        and _semantic_enabled()
    ):
        semantic_scores = _semantic_pair_scores(
            bundle
        )

    candidates: list[
        ComparisonAlignmentHint
    ] = []

    for item_a in bundle.evidence_a:
        for item_b in bundle.evidence_b:
            key = (
                item_a.source_id,
                item_b.source_id,
            )

            lexical = lexical_scores.get(
                key,
                0.0,
            )

            semantic = semantic_scores.get(
                key
            )

            qualifies = (
                lexical >= LEXICAL_ALIGNMENT_THRESHOLD
                or (
                    semantic is not None
                    and semantic >= SEMANTIC_ALIGNMENT_THRESHOLD
                )
            )

            if not qualifies:
                continue

            if (
                semantic is not None
                and semantic >= lexical
            ):
                score = semantic
                method = "semantic"
            else:
                score = lexical
                method = "lexical"

            if _kinds_are_related(
                item_a.kind,
                item_b.kind,
            ):
                score = min(
                    1.0,
                    score + 0.03,
                )

            candidates.append(
                ComparisonAlignmentHint(
                    source_a_id=item_a.source_id,
                    source_b_id=item_b.source_id,
                    score=round(
                        score,
                        4,
                    ),
                    method=method,
                )
            )

    candidates.sort(
        key=lambda hint: (
            -hint.score,
            hint.source_a_id,
            hint.source_b_id,
        )
    )

    selected: list[
        ComparisonAlignmentHint
    ] = []

    a_counts: dict[str, int] = {}
    b_counts: dict[str, int] = {}

    for hint in candidates:
        if len(selected) >= MAX_ALIGNMENT_HINTS:
            break

        if (
            a_counts.get(
                hint.source_a_id,
                0,
            )
            >= MAX_HINTS_PER_SOURCE
        ):
            continue

        if (
            b_counts.get(
                hint.source_b_id,
                0,
            )
            >= MAX_HINTS_PER_SOURCE
        ):
            continue

        selected.append(hint)

        a_counts[
            hint.source_a_id
        ] = (
            a_counts.get(
                hint.source_a_id,
                0,
            )
            + 1
        )

        b_counts[
            hint.source_b_id
        ] = (
            b_counts.get(
                hint.source_b_id,
                0,
            )
            + 1
        )

    return selected


def build_alignment_hint_context(
    hints: list[ComparisonAlignmentHint],
) -> str:
    """
    Format only source relationships for the AI.

    Similarity scores and embedding details intentionally remain backend-only.
    """

    if not hints:
        return (
            "No pre-aligned pairs were strong enough. "
            "Compare the supplied evidence semantically yourself."
        )

    lines = [
        "Likely related evidence pairs:"
    ]

    for hint in hints:
        lines.append(
            f"- {hint.source_a_id} ↔ {hint.source_b_id}"
        )

    return "\n".join(
        lines
    )


def _lexical_pair_scores(
    evidence_a: list[ComparisonEvidence],
    evidence_b: list[ComparisonEvidence],
) -> dict[tuple[str, str], float]:
    scores: dict[
        tuple[str, str],
        float,
    ] = {}

    for item_a in evidence_a:
        for item_b in evidence_b:
            scores[
                (
                    item_a.source_id,
                    item_b.source_id,
                )
            ] = _text_similarity(
                item_a.comparison_text,
                item_b.comparison_text,
            )

    return scores


def _semantic_pair_scores(
    bundle: DocumentComparisonCandidateBundle,
) -> dict[tuple[str, str], float]:
    """Embed all evidence once and build the cross-document similarity matrix."""

    try:
        configuration = get_embedding_configuration()

        all_evidence = bundle.all_evidence

        texts = [
            prepare_comparison_evidence_for_embedding(
                item
            )
            for item in all_evidence
        ]

        if not texts:
            return {}

        client = genai.Client(
            api_key=configuration.api_key
        )

        vectors = _generate_embeddings(
            client=client,
            model=configuration.model,
            dimensions=configuration.dimensions,
            texts=texts,
        )

        if len(vectors) != len(all_evidence):
            return {}

        vector_by_id = {
            evidence.source_id: normalize_vector(
                vector
            )
            for evidence, vector in zip(
                all_evidence,
                vectors,
            )
        }

        scores: dict[
            tuple[str, str],
            float,
        ] = {}

        for item_a in bundle.evidence_a:
            vector_a = vector_by_id.get(
                item_a.source_id
            )

            if vector_a is None:
                continue

            for item_b in bundle.evidence_b:
                vector_b = vector_by_id.get(
                    item_b.source_id
                )

                if vector_b is None:
                    continue

                scores[
                    (
                        item_a.source_id,
                        item_b.source_id,
                    )
                ] = max(
                    -1.0,
                    min(
                        1.0,
                        cosine_similarity(
                            vector_a,
                            vector_b,
                        ),
                    ),
                )

        return scores

    except Exception:
        # Alignment hints are an optimization, not a correctness boundary.
        return {}


def prepare_comparison_evidence_for_embedding(
    item: ComparisonEvidence,
) -> str:
    """Embed only source meaning, without a common boilerplate prefix."""

    parts = [
        item.kind.replace(
            "_",
            " ",
        ),
        item.topic,
        item.statement,
        item.detail,
        item.evidence,
    ]

    return "\n".join(
        part
        for part in (
            _compact_text(
                value,
                1_600,
            )
            for value in parts
        )
        if part
    )


def _semantic_enabled() -> bool:
    raw = os.getenv(
        "DOCUMENT_COMPARISON_SEMANTIC_ALIGNMENT_ENABLED",
        "1",
    ).strip().casefold()

    if raw in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False

    if (
        has_app_context()
        and current_app.config.get(
            "TESTING",
            False,
        )
    ):
        return False

    return True


def _text_similarity(
    first: Any,
    second: Any,
) -> float:
    left = _normalise_text(
        first
    )
    right = _normalise_text(
        second
    )

    if not left or not right:
        return 0.0

    if left == right:
        return 1.0

    sequence = SequenceMatcher(
        None,
        left,
        right,
    ).ratio()

    left_tokens = set(
        left.split()
    )
    right_tokens = set(
        right.split()
    )

    intersection = (
        left_tokens
        & right_tokens
    )

    union = (
        left_tokens
        | right_tokens
    )

    jaccard = (
        len(intersection)
        / len(union)
        if union
        else 0.0
    )

    containment = (
        len(intersection)
        / min(
            len(left_tokens),
            len(right_tokens),
        )
        if (
            left_tokens
            and right_tokens
        )
        else 0.0
    )

    return max(
        sequence,
        jaccard,
        containment,
    )


def _kinds_are_related(
    first: str,
    second: str,
) -> bool:
    first_base = first.split(
        ":",
        1,
    )[0]

    second_base = second.split(
        ":",
        1,
    )[0]

    if first_base == second_base:
        return True

    generic = {
        "key_point",
        "chunk",
        "type_specific",
    }

    return (
        first_base in generic
        or second_base in generic
    )


def _normalise_text(
    value: Any,
) -> str:
    cleaned = re.sub(
        r"[^\w\s]",
        " ",
        str(
            value
            or ""
        ).casefold(),
        flags=re.UNICODE,
    )

    return " ".join(
        cleaned.split()
    )


def _compact_text(
    value: Any,
    max_length: int,
) -> str:
    return " ".join(
        str(
            value
            or ""
        ).split()
    )[:max_length]

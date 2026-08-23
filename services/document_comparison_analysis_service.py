"""Step 13C — structural validation for AI document-comparison drafts.

Step 13C validates the shape and vocabulary of the model output. It does NOT
yet prove that every cited source actually supports the finding. Step 13D owns
that evidence-verification boundary.
"""

from __future__ import annotations

from typing import Any


DOCUMENT_COMPARISON_DRAFT_SCHEMA_VERSION = (
    "document-comparison-draft-v1"
)

ALLOWED_COMPARISON_CATEGORIES = {
    "changed",
    "added",
    "removed",
    "potential_conflict",
}

CATEGORY_ALIASES = {
    "change": "changed",
    "changed": "changed",
    "modified": "changed",
    "addition": "added",
    "added": "added",
    "new": "added",
    "removal": "removed",
    "removed": "removed",
    "deleted": "removed",
    "conflict": "potential_conflict",
    "potential conflict": "potential_conflict",
    "potential_conflict": "potential_conflict",
    "contradiction": "potential_conflict",
}

ALLOWED_CONFIDENCE = {
    "Low",
    "Medium",
    "High",
}

MAX_COMPARISON_FINDINGS = 40
MAX_COMPARISON_SUMMARY_CHARACTERS = 2_400


class DocumentComparisonDraftValidationError(ValueError):
    """Raised when AI comparison output has an unusable structure."""


def normalise_document_comparison_draft(
    value: Any,
) -> dict[str, Any]:
    """Return one safe Step 13C comparison draft."""

    if not isinstance(
        value,
        dict,
    ):
        raise DocumentComparisonDraftValidationError(
            "Document comparison must be a JSON object."
        )

    summary = _clean_text(
        value.get("summary"),
        MAX_COMPARISON_SUMMARY_CHARACTERS,
    )

    raw_findings = value.get(
        "findings"
    )

    if raw_findings is None:
        raw_findings = []

    if not isinstance(
        raw_findings,
        list,
    ):
        raise DocumentComparisonDraftValidationError(
            "Document comparison findings must be a list."
        )

    findings: list[dict[str, Any]] = []

    for raw_finding in raw_findings[
        :MAX_COMPARISON_FINDINGS
    ]:
        finding = _normalise_finding(
            raw_finding
        )

        if finding is not None:
            findings.append(finding)

    if not summary:
        summary = (
            "No material differences were identified."
            if not findings
            else (
                f"LifeOS identified {len(findings)} material "
                "document difference"
                + (
                    "."
                    if len(findings) == 1
                    else "s."
                )
            )
        )

    return {
        "schema_version": DOCUMENT_COMPARISON_DRAFT_SCHEMA_VERSION,
        "summary": summary,
        "findings": findings,
    }


def _normalise_finding(
    value: Any,
) -> dict[str, Any] | None:
    if not isinstance(
        value,
        dict,
    ):
        return None

    category = _normalise_category(
        value.get("category")
    )

    if category is None:
        raise DocumentComparisonDraftValidationError(
            "The comparison returned an unsupported difference category."
        )

    topic = _clean_text(
        value.get("topic")
        or value.get("title"),
        500,
    )

    explanation = _clean_text(
        value.get("explanation")
        or value.get("summary")
        or value.get("detail"),
        1_800,
    )

    if not topic or not explanation:
        raise DocumentComparisonDraftValidationError(
            "Each comparison finding needs a topic and explanation."
        )

    confidence = _clean_confidence(
        value.get("confidence")
    )

    document_a = _normalise_side(
        value.get("document_a"),
        expected_prefix="A",
    )

    document_b = _normalise_side(
        value.get("document_b"),
        expected_prefix="B",
    )

    return {
        "category": category,
        "topic": topic,
        "explanation": explanation,
        "confidence": confidence,
        "document_a": document_a,
        "document_b": document_b,
    }


def _normalise_side(
    value: Any,
    *,
    expected_prefix: str,
) -> dict[str, Any]:
    raw = (
        value
        if isinstance(
            value,
            dict,
        )
        else {}
    )

    raw_ids = raw.get(
        "source_ids"
    )

    if raw_ids is None:
        raw_ids = []

    if not isinstance(
        raw_ids,
        list,
    ):
        raw_ids = [
            raw_ids
        ]

    source_ids: list[str] = []
    seen: set[str] = set()

    for raw_id in raw_ids:
        source_id = _clean_text(
            raw_id,
            20,
        ).upper()

        if not source_id.startswith(
            expected_prefix
        ):
            continue

        numeric_part = source_id[1:]

        if (
            not numeric_part.isdigit()
            or int(numeric_part) <= 0
            or source_id in seen
        ):
            continue

        seen.add(source_id)
        source_ids.append(source_id)

    return {
        "statement": _clean_text(
            raw.get("statement")
            or raw.get("text"),
            1_200,
        ),
        "source_ids": source_ids,
    }


def _normalise_category(
    value: Any,
) -> str | None:
    cleaned = (
        _clean_text(
            value,
            80,
        )
        .replace("-", " ")
        .replace("_", " ")
        .casefold()
    )

    category = CATEGORY_ALIASES.get(
        cleaned
    )

    if category in ALLOWED_COMPARISON_CATEGORIES:
        return category

    return None


def _clean_confidence(
    value: Any,
) -> str:
    cleaned = _clean_text(
        value,
        30,
    ).title()

    return (
        cleaned
        if cleaned in ALLOWED_CONFIDENCE
        else "Medium"
    )


def _clean_text(
    value: Any,
    max_length: int,
) -> str:
    return " ".join(
        str(
            value
            or ""
        ).split()
    )[:max_length]

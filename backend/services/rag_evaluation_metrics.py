"""Pure metric helpers for Step 18 RAG evaluation.

This module intentionally has no Flask/SQLAlchemy imports so the scoring rules can
be tested in isolation and reused by CI/reporting tooling.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable


PAGE_RANGE_RE = re.compile(r"^\s*(\d+)\s*[-–—]\s*(\d+)\s*$")
NON_WORD_RE = re.compile(r"[^\w.%+/-]+", flags=re.UNICODE)
WHITESPACE_RE = re.compile(r"\s+")


def normalize_answer_text(value: Any) -> str:
    """Normalize answer text for resilient gold-string checks.

    We intentionally do not perform semantic grading here. The evaluator should
    fail predictably when a required fact disappears, while tolerating harmless
    punctuation/case/number-formatting differences such as ``3,250`` vs ``3250``.
    """

    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = text.replace(",", "")
    text = text.replace("–", "-").replace("—", "-")
    text = NON_WORD_RE.sub(" ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def answer_text_checks(
    *,
    answer: str,
    required: Iterable[str] | None = None,
    forbidden: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Score deterministic required/forbidden answer phrases."""

    normalized_answer = normalize_answer_text(answer)
    required_values = [str(item) for item in (required or []) if str(item).strip()]
    forbidden_values = [str(item) for item in (forbidden or []) if str(item).strip()]

    missing = [
        item
        for item in required_values
        if normalize_answer_text(item) not in normalized_answer
    ]
    present_forbidden = [
        item
        for item in forbidden_values
        if normalize_answer_text(item) in normalized_answer
    ]

    applicable = bool(required_values or forbidden_values)
    passed = not missing and not present_forbidden

    return {
        "applicable": applicable,
        "passed": passed,
        "missing_required": missing,
        "present_forbidden": present_forbidden,
        "required_count": len(required_values),
        "forbidden_count": len(forbidden_values),
    }


def page_matches(expected: Any, actual: Any) -> bool:
    """Return whether a cited/retrieved page satisfies a gold page selector."""

    if expected in (None, ""):
        return True
    if actual in (None, ""):
        return False

    expected_pages = _page_set(expected)
    actual_pages = _page_set(actual)
    if expected_pages and actual_pages:
        return bool(expected_pages & actual_pages)

    return str(expected).strip().casefold() == str(actual).strip().casefold()


def source_matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    """Match one expected source selector against one actual source."""

    expected_document_id = expected.get("document_id")
    if expected_document_id is not None:
        try:
            if int(actual.get("document_id")) != int(expected_document_id):
                return False
        except (TypeError, ValueError):
            return False

    expected_filename = str(expected.get("filename") or "").strip()
    if expected_filename:
        if str(actual.get("filename") or "").strip().casefold() != expected_filename.casefold():
            return False

    expected_content_type = str(expected.get("content_type") or "").strip()
    if expected_content_type:
        if (
            str(actual.get("content_type") or "text").strip().casefold()
            != expected_content_type.casefold()
        ):
            return False

    if "page" in expected and not page_matches(expected.get("page"), actual.get("page")):
        return False

    section_contains = str(expected.get("section_contains") or "").strip()
    if section_contains:
        actual_section = normalize_answer_text(actual.get("section"))
        if normalize_answer_text(section_contains) not in actual_section:
            return False

    evidence_contains = expected.get("evidence_contains")
    if evidence_contains:
        required_evidence = (
            [evidence_contains]
            if isinstance(evidence_contains, str)
            else list(evidence_contains)
        )
        actual_evidence = normalize_answer_text(actual.get("evidence"))
        for phrase in required_evidence:
            if normalize_answer_text(phrase) not in actual_evidence:
                return False

    return True


def source_expectation_metrics(
    *,
    expected_sources: Iterable[dict[str, Any]] | None,
    actual_sources: Iterable[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Compute recall and reciprocal rank for expected source selectors."""

    expected = [dict(item) for item in (expected_sources or [])]
    actual = [dict(item) for item in (actual_sources or [])]

    if not expected:
        return {
            "applicable": False,
            "expected_count": 0,
            "hit_count": 0,
            "recall": None,
            "all_expected_found": True,
            "reciprocal_rank": None,
            "matches": [],
        }

    matches: list[dict[str, Any]] = []
    matched_ranks: list[int] = []

    for index, selector in enumerate(expected, start=1):
        rank = None
        matched_source = None
        for actual_index, source in enumerate(actual, start=1):
            if source_matches(selector, source):
                rank = actual_index
                matched_source = source
                break

        if rank is not None:
            matched_ranks.append(rank)

        matches.append(
            {
                "expected_index": index,
                "expected": selector,
                "found": rank is not None,
                "rank": rank,
                "actual": matched_source,
            }
        )

    hit_count = len(matched_ranks)
    recall = hit_count / len(expected)
    reciprocal_rank = (1.0 / min(matched_ranks)) if matched_ranks else 0.0

    return {
        "applicable": True,
        "expected_count": len(expected),
        "hit_count": hit_count,
        "recall": recall,
        "all_expected_found": hit_count == len(expected),
        "reciprocal_rank": reciprocal_rank,
        "matches": matches,
    }


def mean(values: Iterable[float | None]) -> float | None:
    usable = [float(value) for value in values if value is not None]
    if not usable:
        return None
    return sum(usable) / len(usable)


def _page_set(value: Any) -> set[int]:
    if isinstance(value, int):
        return {value}

    text = str(value or "").strip()
    if text.isdigit():
        return {int(text)}

    match = PAGE_RANGE_RE.match(text)
    if not match:
        return set()

    start = int(match.group(1))
    end = int(match.group(2))
    if start > end or end - start > 1000:
        return set()
    return set(range(start, end + 1))

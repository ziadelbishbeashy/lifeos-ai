"""Quality scoring and candidate selection for adaptive OCR."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ocr.base import OCRAttempt, OCRPageResult
from ocr.quality import ACCEPTABLE, GOOD, POOR, classify_ocr_quality


@dataclass(frozen=True)
class EvaluatedOCRResult:
    result: OCRPageResult
    quality: str
    character_count: int
    word_count: int
    score: float


_QUALITY_RANK = {
    POOR: 0.0,
    ACCEPTABLE: 1.0,
    GOOD: 2.0,
}


def count_ocr_words(text: str) -> int:
    return len([part for part in re.split(r"\s+", str(text or "").strip()) if part])


def evaluate_ocr_page_result(result: OCRPageResult) -> EvaluatedOCRResult:
    """Evaluate one OCR result using volume, confidence and text sanity.

    Quality rank dominates the numeric score. Within the same quality bucket,
    useful text volume and confidence decide the winner. This keeps a large but
    low-confidence blob from beating a smaller, clearly readable result merely
    because it contains more characters.
    """

    text = str(result.text or "").strip()
    character_count = len(text)
    word_count = count_ocr_words(text)
    confidence = result.confidence
    quality = classify_ocr_quality(
        character_count=character_count,
        word_count=word_count,
        average_confidence=confidence,
    )

    non_space = [char for char in text if not char.isspace()]
    alphanumeric_ratio = (
        sum(1 for char in non_space if char.isalnum()) / len(non_space)
        if non_space
        else 0.0
    )
    confidence_score = 0.5 if confidence is None else max(0.0, min(1.0, float(confidence)))
    char_coverage = min(1.0, character_count / 400.0)
    word_coverage = min(1.0, word_count / 40.0)

    score = (
        _QUALITY_RANK.get(quality, 0.0) * 10.0
        + char_coverage * 2.0
        + word_coverage * 2.0
        + confidence_score * 3.0
        + alphanumeric_ratio
    )

    return EvaluatedOCRResult(
        result=result,
        quality=quality,
        character_count=character_count,
        word_count=word_count,
        score=score,
    )


def make_attempt(
    evaluated: EvaluatedOCRResult,
    *,
    provider: str,
    strategy: str | None,
    error: str | None = None,
) -> OCRAttempt:
    return OCRAttempt(
        provider=provider,
        strategy=strategy,
        quality=evaluated.quality,
        character_count=evaluated.character_count,
        word_count=evaluated.word_count,
        confidence=evaluated.result.confidence,
        score=round(float(evaluated.score), 6),
        error=error,
    )


def choose_best_ocr_result(
    candidates: list[tuple[OCRPageResult, str, str | None]],
) -> tuple[OCRPageResult, tuple[OCRAttempt, ...]]:
    """Return the strongest candidate and a complete attempt audit trail."""

    if not candidates:
        raise ValueError("At least one OCR candidate is required.")

    evaluated: list[tuple[EvaluatedOCRResult, str, str | None]] = []
    attempts: list[OCRAttempt] = []
    for result, provider, strategy in candidates:
        item = evaluate_ocr_page_result(result)
        evaluated.append((item, provider, strategy))
        attempts.append(make_attempt(item, provider=provider, strategy=strategy))

    winner, provider, strategy = max(
        evaluated,
        key=lambda item: (
            item[0].score,
            item[0].character_count,
            item[0].word_count,
            item[0].result.confidence or 0.0,
        ),
    )

    result = OCRPageResult(
        text=winner.result.text,
        confidence=winner.result.confidence,
        words=tuple(winner.result.words or ()),
        provider_name=provider,
        strategy=strategy,
        quality=winner.quality,
        attempts=tuple(attempts),
    )
    return result, tuple(attempts)

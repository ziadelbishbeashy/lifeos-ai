"""OCR quality classification for observability.

A run that returns without raising an exception is not the same as a run that
produced useful text. The classifier considers both text volume and OCR
confidence. Document-level calls can pass ``page_count`` so a tiny amount of
text spread across many pages is correctly classified as poor.
"""

from __future__ import annotations

GOOD = "good"
ACCEPTABLE = "acceptable"
POOR = "poor"

_GOOD_MIN_CHARACTERS_PER_PAGE = 400
_GOOD_MIN_WORDS_PER_PAGE = 40
_GOOD_MIN_CONFIDENCE = 0.80

_ACCEPTABLE_MIN_CHARACTERS_PER_PAGE = 120
_ACCEPTABLE_MIN_WORDS_PER_PAGE = 12
_ACCEPTABLE_MIN_CONFIDENCE = 0.55


def classify_ocr_quality(
    *,
    character_count: int,
    word_count: int,
    average_confidence: float | None,
    page_count: int = 1,
) -> str:
    """Classify one page's or one document's OCR/native text output.

    Volume thresholds scale with ``page_count``. This matters for documents:
    303 characters can be reasonable for one sparse page but is clearly poor
    when it is all that was recovered from a six-page lecture.

    When confidence is unavailable (native-only text), volume alone is judged.
    """

    character_count = max(0, int(character_count or 0))
    word_count = max(0, int(word_count or 0))
    page_count = max(1, int(page_count or 1))

    if character_count <= 0 or word_count <= 0:
        return POOR

    good_chars = _GOOD_MIN_CHARACTERS_PER_PAGE * page_count
    good_words = _GOOD_MIN_WORDS_PER_PAGE * page_count
    acceptable_chars = _ACCEPTABLE_MIN_CHARACTERS_PER_PAGE * page_count
    acceptable_words = _ACCEPTABLE_MIN_WORDS_PER_PAGE * page_count

    if average_confidence is None:
        if character_count >= good_chars and word_count >= good_words:
            return GOOD
        if character_count >= acceptable_chars and word_count >= acceptable_words:
            return ACCEPTABLE
        return POOR

    confidence = max(0.0, min(1.0, float(average_confidence)))

    if (
        confidence >= _GOOD_MIN_CONFIDENCE
        and character_count >= good_chars
        and word_count >= good_words
    ):
        return GOOD

    if (
        confidence >= _ACCEPTABLE_MIN_CONFIDENCE
        and character_count >= acceptable_chars
        and word_count >= acceptable_words
    ):
        return ACCEPTABLE

    return POOR

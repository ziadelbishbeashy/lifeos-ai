"""OCR quality classifier boundaries."""

from ocr.quality import ACCEPTABLE, GOOD, POOR, classify_ocr_quality


def test_quality_is_poor_when_volume_is_tiny_even_with_high_confidence():
    assert classify_ocr_quality(
        character_count=303,
        word_count=35,
        average_confidence=0.95,
        page_count=5,
    ) == POOR


def test_quality_is_good_when_volume_and_confidence_are_strong():
    assert classify_ocr_quality(
        character_count=1200,
        word_count=180,
        average_confidence=0.91,
    ) == GOOD


def test_quality_is_acceptable_for_middle_tier_ocr():
    assert classify_ocr_quality(
        character_count=300,
        word_count=35,
        average_confidence=0.72,
    ) == ACCEPTABLE


def test_native_text_without_confidence_is_classified_by_volume_only():
    assert classify_ocr_quality(
        character_count=900,
        word_count=120,
        average_confidence=None,
    ) == GOOD
    assert classify_ocr_quality(
        character_count=150,
        word_count=15,
        average_confidence=None,
    ) == ACCEPTABLE
    assert classify_ocr_quality(
        character_count=40,
        word_count=5,
        average_confidence=None,
    ) == POOR

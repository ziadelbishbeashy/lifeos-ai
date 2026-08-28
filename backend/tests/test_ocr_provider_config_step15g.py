"""Pure parsing tests for adaptive OCR configuration helpers."""

from ocr.service import _parse_psm_modes


def test_psm_modes_are_cleaned_and_deduplicated():
    assert _parse_psm_modes("3, 6, 11,6,bad,99") == (3, 6, 11)


def test_invalid_psm_config_falls_back_to_default_modes():
    assert _parse_psm_modes("bad,99") == (3, 6, 11)

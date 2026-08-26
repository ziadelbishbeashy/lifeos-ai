"""Resolve the configured OCR provider."""

from __future__ import annotations

from flask import current_app

from ocr.base import OCRConfigurationError, OCRProvider
from ocr.providers.tesseract import TesseractOCRProvider


def get_ocr_provider() -> OCRProvider:
    provider_name = str(
        current_app.config.get("OCR_PROVIDER", "disabled") or "disabled"
    ).strip().lower()

    if provider_name in {"", "disabled", "none", "off"}:
        raise OCRConfigurationError(
            "OCR is disabled. Set OCR_PROVIDER=tesseract after installing Tesseract."
        )

    if provider_name == "tesseract":
        return TesseractOCRProvider(
            languages=str(current_app.config.get("OCR_LANGUAGES", "eng") or "eng"),
            executable=current_app.config.get("OCR_TESSERACT_CMD"),
        )

    raise OCRConfigurationError(
        f'Unsupported OCR provider "{provider_name}".'
    )

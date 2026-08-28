"""Resolve the configured OCR provider."""

from __future__ import annotations

from flask import current_app

from ocr.base import OCRConfigurationError, OCRProvider
from ocr.providers.adaptive import AdaptiveOCRProvider
from ocr.providers.easyocr import EasyOCRProvider
from ocr.providers.tesseract import DEFAULT_PSM_MODES, TesseractOCRProvider


_TESSERACT_TO_EASYOCR_LANGUAGE = {
    "eng": "en",
    "ara": "ar",
    "fra": "fr",
    "deu": "de",
    "spa": "es",
    "ita": "it",
    "por": "pt",
    "rus": "ru",
    "tur": "tr",
}


def get_ocr_provider() -> OCRProvider:
    provider_name = str(
        current_app.config.get("OCR_PROVIDER", "disabled") or "disabled"
    ).strip().lower()

    if provider_name in {"", "disabled", "none", "off"}:
        raise OCRConfigurationError(
            "OCR is disabled. Set OCR_PROVIDER=tesseract after installing Tesseract."
        )

    if provider_name == "tesseract":
        primary = TesseractOCRProvider(
            languages=str(current_app.config.get("OCR_LANGUAGES", "eng") or "eng"),
            executable=current_app.config.get("OCR_TESSERACT_CMD"),
            psm_modes=_parse_psm_modes(
                current_app.config.get("OCR_TESSERACT_PSM_MODES", "3,6,11")
            ),
        )
        if not bool(current_app.config.get("OCR_EASYOCR_ENABLED", False)):
            return primary

        fallback = EasyOCRProvider(
            languages=_easyocr_languages(),
            gpu=bool(current_app.config.get("OCR_EASYOCR_GPU", False)),
            model_storage_directory=current_app.config.get("OCR_EASYOCR_MODEL_DIR"),
            download_enabled=bool(
                current_app.config.get("OCR_EASYOCR_DOWNLOAD_ENABLED", True)
            ),
        )
        return AdaptiveOCRProvider(primary=primary, fallback=fallback)

    if provider_name == "easyocr":
        return EasyOCRProvider(
            languages=_easyocr_languages(),
            gpu=bool(current_app.config.get("OCR_EASYOCR_GPU", False)),
            model_storage_directory=current_app.config.get("OCR_EASYOCR_MODEL_DIR"),
            download_enabled=bool(
                current_app.config.get("OCR_EASYOCR_DOWNLOAD_ENABLED", True)
            ),
        )

    raise OCRConfigurationError(
        f'Unsupported OCR provider "{provider_name}".'
    )


def _parse_psm_modes(value) -> tuple[int, ...]:
    raw_values = value if isinstance(value, (list, tuple)) else str(value or "").split(",")
    modes: list[int] = []
    for item in raw_values:
        try:
            mode = int(str(item).strip())
        except (TypeError, ValueError):
            continue
        if 0 <= mode <= 13 and mode not in modes:
            modes.append(mode)
    return tuple(modes or DEFAULT_PSM_MODES)


def _easyocr_languages() -> tuple[str, ...]:
    configured = str(current_app.config.get("OCR_EASYOCR_LANGUAGES", "") or "").strip()
    if configured:
        values = [part.strip() for part in configured.replace("+", ",").split(",")]
        languages = tuple(value for value in values if value)
        if languages:
            return languages

    tesseract_languages = str(
        current_app.config.get("OCR_LANGUAGES", "eng") or "eng"
    ).replace(",", "+")
    mapped: list[str] = []
    for code in tesseract_languages.split("+"):
        cleaned = code.strip().lower()
        if not cleaned:
            continue
        easy_code = _TESSERACT_TO_EASYOCR_LANGUAGE.get(cleaned)
        if easy_code and easy_code not in mapped:
            mapped.append(easy_code)
    return tuple(mapped or ["en"])

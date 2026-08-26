"""Local Tesseract OCR provider.

Tesseract itself is an OS-level executable. ``pytesseract`` is only the Python
adapter. Keeping this behind the provider boundary lets LifeOS swap to a managed
OCR provider later without changing Document Brain or RAG code.
"""

from __future__ import annotations

from io import BytesIO

from ocr.base import OCRConfigurationError, OCRPageResult, OCRProvider, OCRProviderError, OCRWord


class TesseractOCRProvider(OCRProvider):
    name = "tesseract"

    def __init__(
        self,
        *,
        languages: str = "eng",
        executable: str | None = None,
    ) -> None:
        self.languages = str(languages or "eng").strip() or "eng"
        self.executable = str(executable or "").strip() or None

    def recognize_page(
        self,
        image_bytes: bytes,
        *,
        page_number: int,
    ) -> OCRPageResult:
        if not image_bytes:
            raise OCRProviderError(
                f"Page {page_number} could not be sent to OCR because its image is empty."
            )

        try:
            import pytesseract
            from PIL import Image
        except ImportError as error:  # pragma: no cover - environment guard
            raise OCRConfigurationError(
                "Tesseract OCR Python dependencies are not installed."
            ) from error

        if self.executable:
            pytesseract.pytesseract.tesseract_cmd = self.executable

        try:
            image = Image.open(BytesIO(image_bytes))
            text = pytesseract.image_to_string(
                image,
                lang=self.languages,
                config="--psm 3",
            )
            data = pytesseract.image_to_data(
                image,
                lang=self.languages,
                config="--psm 3",
                output_type=pytesseract.Output.DICT,
            )
        except pytesseract.TesseractNotFoundError as error:
            raise OCRConfigurationError(
                "Tesseract is not installed or OCR_TESSERACT_CMD does not point to it."
            ) from error
        except pytesseract.TesseractError as error:
            raise OCRProviderError(
                f"Tesseract could not recognize PDF page {page_number}."
            ) from error
        except Exception as error:
            raise OCRProviderError(
                f"LifeOS could not OCR PDF page {page_number}."
            ) from error

        confidences: list[float] = []
        words: list[OCRWord] = []
        image_width = max(1, int(getattr(image, "width", 1) or 1))
        image_height = max(1, int(getattr(image, "height", 1) or 1))

        raw_text = data.get("text", [])
        raw_conf = data.get("conf", [])
        raw_left = data.get("left", [])
        raw_top = data.get("top", [])
        raw_width = data.get("width", [])
        raw_height = data.get("height", [])
        row_count = max(
            len(raw_text), len(raw_conf), len(raw_left),
            len(raw_top), len(raw_width), len(raw_height),
        )

        for index in range(row_count):
            token = str(raw_text[index] if index < len(raw_text) else "").strip()
            try:
                raw_value = float(raw_conf[index] if index < len(raw_conf) else -1)
            except (TypeError, ValueError):
                raw_value = -1

            word_confidence = raw_value / 100.0 if raw_value >= 0 else None
            if word_confidence is not None:
                confidences.append(word_confidence)

            if not token:
                continue

            try:
                left = float(raw_left[index])
                top = float(raw_top[index])
                width = float(raw_width[index])
                height = float(raw_height[index])
            except (IndexError, TypeError, ValueError):
                continue

            if width <= 0 or height <= 0:
                continue

            words.append(
                OCRWord(
                    text=token,
                    left=max(0.0, min(1.0, left / image_width)),
                    top=max(0.0, min(1.0, top / image_height)),
                    width=max(0.0, min(1.0, width / image_width)),
                    height=max(0.0, min(1.0, height / image_height)),
                    confidence=word_confidence,
                )
            )

        confidence = (
            sum(confidences) / len(confidences)
            if confidences
            else None
        )

        return OCRPageResult(
            text=str(text or ""),
            confidence=confidence,
            words=tuple(words),
        )

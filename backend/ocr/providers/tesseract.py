"""Local Tesseract OCR provider with multi-pass page segmentation.

Tesseract itself is an OS-level executable. ``pytesseract`` is only the Python
adapter. LifeOS tries several PSM strategies on difficult slide/scan layouts
and keeps the strongest result before considering a secondary OCR provider.
"""

from __future__ import annotations

from io import BytesIO

from ocr.base import OCRConfigurationError, OCRPageResult, OCRProvider, OCRProviderError, OCRWord
from ocr.quality import POOR
from ocr.selection import choose_best_ocr_result, evaluate_ocr_page_result


DEFAULT_PSM_MODES = (3, 6, 11)


class TesseractOCRProvider(OCRProvider):
    name = "tesseract"

    def __init__(
        self,
        *,
        languages: str = "eng",
        executable: str | None = None,
        psm_modes: tuple[int, ...] | list[int] = DEFAULT_PSM_MODES,
    ) -> None:
        self.languages = str(languages or "eng").strip() or "eng"
        self.executable = str(executable or "").strip() or None
        cleaned_modes: list[int] = []
        for value in psm_modes or DEFAULT_PSM_MODES:
            try:
                mode = int(value)
            except (TypeError, ValueError):
                continue
            if 0 <= mode <= 13 and mode not in cleaned_modes:
                cleaned_modes.append(mode)
        self.psm_modes = tuple(cleaned_modes or DEFAULT_PSM_MODES)

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
            image.load()
        except Exception as error:
            raise OCRProviderError(
                f"LifeOS could not open OCR image for PDF page {page_number}."
            ) from error

        candidates: list[tuple[OCRPageResult, str, str | None]] = []
        errors: list[str] = []
        for psm in self.psm_modes:
            try:
                result = self._recognize_with_psm(
                    image,
                    page_number=page_number,
                    psm=psm,
                    pytesseract=pytesseract,
                )
                candidates.append((result, self.name, f"psm_{psm}"))
                # Avoid paying for every PSM when an earlier pass already
                # recovered enough readable text. Poor pages continue through
                # the configured strategies, then the strongest pass wins.
                if evaluate_ocr_page_result(result).quality != POOR:
                    break
            except pytesseract.TesseractNotFoundError as error:
                raise OCRConfigurationError(
                    "Tesseract is not installed or OCR_TESSERACT_CMD does not point to it."
                ) from error
            except pytesseract.TesseractError as error:
                errors.append(f"psm_{psm}: {error}")
            except Exception as error:
                errors.append(f"psm_{psm}: {type(error).__name__}")

        if not candidates:
            detail = "; ".join(errors[:3])
            suffix = f" ({detail})" if detail else ""
            raise OCRProviderError(
                f"Tesseract could not recognize PDF page {page_number}{suffix}."
            )

        winner, _attempts = choose_best_ocr_result(candidates)
        return winner

    def _recognize_with_psm(self, image, *, page_number: int, psm: int, pytesseract) -> OCRPageResult:
        """Run one Tesseract pass using a single image_to_data subprocess.

        We reconstruct readable lines from TSV token metadata instead of running
        both ``image_to_string`` and ``image_to_data``. That keeps three PSM
        passes practical on CPU while still preserving bounding boxes.
        """

        data = pytesseract.image_to_data(
            image,
            lang=self.languages,
            config=f"--psm {psm}",
            output_type=pytesseract.Output.DICT,
        )

        image_width = max(1, int(getattr(image, "width", 1) or 1))
        image_height = max(1, int(getattr(image, "height", 1) or 1))
        raw_text = data.get("text", [])
        raw_conf = data.get("conf", [])
        raw_left = data.get("left", [])
        raw_top = data.get("top", [])
        raw_width = data.get("width", [])
        raw_height = data.get("height", [])
        raw_block = data.get("block_num", [])
        raw_par = data.get("par_num", [])
        raw_line = data.get("line_num", [])

        row_count = max(
            len(raw_text), len(raw_conf), len(raw_left), len(raw_top),
            len(raw_width), len(raw_height), len(raw_block), len(raw_par), len(raw_line),
        )

        confidences: list[float] = []
        words: list[OCRWord] = []
        line_tokens: dict[tuple[int, int, int], list[tuple[int, str]]] = {}

        for index in range(row_count):
            token = str(raw_text[index] if index < len(raw_text) else "").strip()
            if not token:
                continue

            try:
                raw_value = float(raw_conf[index] if index < len(raw_conf) else -1)
            except (TypeError, ValueError):
                raw_value = -1
            word_confidence = raw_value / 100.0 if raw_value >= 0 else None
            if word_confidence is not None:
                confidences.append(word_confidence)

            try:
                left = float(raw_left[index])
                top = float(raw_top[index])
                width = float(raw_width[index])
                height = float(raw_height[index])
            except (IndexError, TypeError, ValueError):
                left = top = width = height = 0.0

            if width > 0 and height > 0:
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

            def _int_at(values, default=0):
                try:
                    return int(values[index]) if index < len(values) else default
                except (TypeError, ValueError):
                    return default

            line_key = (
                _int_at(raw_block),
                _int_at(raw_par),
                _int_at(raw_line),
            )
            line_tokens.setdefault(line_key, []).append((index, token))

        lines = [
            " ".join(token for _index, token in sorted(tokens, key=lambda item: item[0]))
            for _key, tokens in sorted(line_tokens.items(), key=lambda item: min(x[0] for x in item[1]))
            if tokens
        ]
        text = "\n".join(line for line in lines if line.strip()).strip()
        confidence = sum(confidences) / len(confidences) if confidences else None

        return OCRPageResult(
            text=text,
            confidence=confidence,
            words=tuple(words),
            provider_name=self.name,
            strategy=f"psm_{psm}",
        )

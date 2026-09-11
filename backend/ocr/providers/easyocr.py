"""EasyOCR fallback provider.

EasyOCR is intentionally optional. LifeOS only initializes its relatively heavy
model when the adaptive provider actually needs a fallback for a poor
Tesseract page.
"""

from __future__ import annotations

from io import BytesIO
from threading import Lock
from typing import Callable

from ocr.base import OCRConfigurationError, OCRPageResult, OCRProvider, OCRProviderError, OCRWord
from ocr.selection import evaluate_ocr_page_result, make_attempt


class EasyOCRProvider(OCRProvider):
    name = "easyocr"
    _reader_cache: dict[tuple, object] = {}
    _reader_lock = Lock()

    def __init__(
        self,
        *,
        languages: tuple[str, ...] | list[str] = ("en",),
        gpu: bool = False,
        model_storage_directory: str | None = None,
        download_enabled: bool = True,
        reader_factory: Callable[..., object] | None = None,
    ) -> None:
        cleaned = tuple(str(value).strip() for value in languages if str(value).strip())
        self.languages = cleaned or ("en",)
        self.gpu = bool(gpu)
        self.model_storage_directory = str(model_storage_directory or "").strip() or None
        self.download_enabled = bool(download_enabled)
        self.reader_factory = reader_factory

    def recognize_page(self, image_bytes: bytes, *, page_number: int) -> OCRPageResult:
        if not image_bytes:
            raise OCRProviderError(
                f"Page {page_number} could not be sent to EasyOCR because its image is empty."
            )

        try:
            from PIL import Image
        except ImportError as error:  # pragma: no cover
            raise OCRConfigurationError("Pillow is required for EasyOCR fallback.") from error

        try:
            image = Image.open(BytesIO(image_bytes))
            image.load()
            image_width = max(1, int(image.width or 1))
            image_height = max(1, int(image.height or 1))
        except Exception as error:
            raise OCRProviderError(
                f"LifeOS could not open the EasyOCR image for PDF page {page_number}."
            ) from error

        reader = self._get_reader()
        try:
            detections = reader.readtext(
                image_bytes,
                detail=1,
                paragraph=False,
            )
        except Exception as error:
            raise OCRProviderError(
                f"EasyOCR could not recognize PDF page {page_number}."
            ) from error

        items: list[tuple[float, float, str, float | None, tuple[float, float, float, float]]] = []
        all_words: list[OCRWord] = []
        confidences: list[float] = []

        for detection in detections or []:
            if not isinstance(detection, (list, tuple)) or len(detection) < 2:
                continue
            bbox = detection[0]
            text = str(detection[1] or "").strip()
            if not text:
                continue
            try:
                confidence = float(detection[2]) if len(detection) >= 3 else None
            except (TypeError, ValueError):
                confidence = None
            if confidence is not None:
                confidence = max(0.0, min(1.0, confidence))
                confidences.append(confidence)

            bounds = _bbox_bounds(bbox)
            if bounds is None:
                continue
            left, top, right, bottom = bounds
            items.append((top, left, text, confidence, bounds))
            all_words.extend(
                _split_detection_words(
                    text=text,
                    bounds=bounds,
                    confidence=confidence,
                    image_width=image_width,
                    image_height=image_height,
                )
            )

        items.sort(key=lambda item: (round(item[0] / max(1.0, image_height) * 100.0), item[1]))
        text = "\n".join(item[2] for item in items).strip()
        average_confidence = sum(confidences) / len(confidences) if confidences else None

        result = OCRPageResult(
            text=text,
            confidence=average_confidence,
            words=tuple(all_words),
            provider_name=self.name,
            strategy="standard",
        )
        evaluated = evaluate_ocr_page_result(result)
        attempt = make_attempt(evaluated, provider=self.name, strategy="standard")
        return OCRPageResult(
            text=result.text,
            confidence=result.confidence,
            words=result.words,
            provider_name=self.name,
            strategy="standard",
            quality=evaluated.quality,
            attempts=(attempt,),
        )

    def _get_reader(self):
        if self.reader_factory is not None:
            return self.reader_factory(
                list(self.languages),
                gpu=self.gpu,
                model_storage_directory=self.model_storage_directory,
                download_enabled=self.download_enabled,
            )

        try:
            import easyocr
        except ImportError as error:  # pragma: no cover - environment guard
            raise OCRConfigurationError(
                "EasyOCR fallback is enabled but the easyocr package is not installed."
            ) from error

        key = (
            self.languages,
            self.gpu,
            self.model_storage_directory,
            self.download_enabled,
        )
        with self._reader_lock:
            existing = self._reader_cache.get(key)
            if existing is not None:
                return existing
            kwargs = {
                "gpu": self.gpu,
                "download_enabled": self.download_enabled,
            }
            if self.model_storage_directory:
                kwargs["model_storage_directory"] = self.model_storage_directory
            reader = easyocr.Reader(list(self.languages), **kwargs)
            self._reader_cache[key] = reader
            return reader


def _bbox_bounds(bbox) -> tuple[float, float, float, float] | None:
    try:
        points = list(bbox or [])
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
    except (TypeError, ValueError, IndexError):
        return None
    if not xs or not ys:
        return None
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _split_detection_words(
    *,
    text: str,
    bounds: tuple[float, float, float, float],
    confidence: float | None,
    image_width: int,
    image_height: int,
) -> list[OCRWord]:
    """Approximate token boxes inside an EasyOCR phrase box.

    EasyOCR commonly returns a phrase/line box rather than one box per word.
    Splitting the box proportionally by token length preserves a useful
    selectable PDF text layer without pretending the provider supplied exact
    per-token geometry.
    """

    tokens = [token for token in text.split() if token]
    if not tokens:
        return []
    left, top, right, bottom = bounds
    total_width = max(1.0, right - left)
    total_units = sum(max(1, len(token)) for token in tokens) + max(0, len(tokens) - 1)
    cursor_units = 0
    words: list[OCRWord] = []
    for token in tokens:
        units = max(1, len(token))
        token_left = left + total_width * (cursor_units / total_units)
        token_right = left + total_width * ((cursor_units + units) / total_units)
        cursor_units += units + 1
        words.append(
            OCRWord(
                text=token,
                left=max(0.0, min(1.0, token_left / image_width)),
                top=max(0.0, min(1.0, top / image_height)),
                width=max(0.0, min(1.0, (token_right - token_left) / image_width)),
                height=max(0.0, min(1.0, (bottom - top) / image_height)),
                confidence=confidence,
            )
        )
    return words

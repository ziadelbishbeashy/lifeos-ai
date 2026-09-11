"""Adaptive page-level OCR: multi-pass Tesseract with EasyOCR fallback."""

from __future__ import annotations

from ocr.base import OCRAttempt, OCRConfigurationError, OCRPageResult, OCRProvider, OCRError
from ocr.quality import POOR
from ocr.selection import evaluate_ocr_page_result, make_attempt


class AdaptiveOCRProvider(OCRProvider):
    """Prefer Tesseract, but rescue genuinely poor pages with EasyOCR."""

    name = "adaptive"

    def __init__(
        self,
        *,
        primary: OCRProvider,
        fallback: OCRProvider | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback

    def recognize_page(self, image_bytes: bytes, *, page_number: int) -> OCRPageResult:
        primary_result = self.primary.recognize_page(image_bytes, page_number=page_number)
        primary_eval = evaluate_ocr_page_result(primary_result)
        primary_attempts = tuple(primary_result.attempts or ()) or (
            make_attempt(
                primary_eval,
                provider=primary_result.provider_name or self.primary.name,
                strategy=primary_result.strategy,
            ),
        )

        # Good/acceptable Tesseract output is intentionally kept. EasyOCR is a
        # rescue path, not a mandatory second pass on every page.
        if self.fallback is None or primary_eval.quality != POOR:
            return _decorate(
                primary_result,
                quality=primary_eval.quality,
                attempts=primary_attempts,
            )

        try:
            fallback_result = self.fallback.recognize_page(
                image_bytes,
                page_number=page_number,
            )
            fallback_eval = evaluate_ocr_page_result(fallback_result)
            fallback_attempts = tuple(fallback_result.attempts or ()) or (
                make_attempt(
                    fallback_eval,
                    provider=fallback_result.provider_name or self.fallback.name,
                    strategy=fallback_result.strategy,
                ),
            )
        except OCRError as error:
            failed = OCRAttempt(
                provider=getattr(self.fallback, "name", "fallback"),
                strategy=None,
                quality=POOR,
                character_count=0,
                word_count=0,
                confidence=None,
                score=0.0,
                error=str(error),
            )
            return _decorate(
                primary_result,
                quality=primary_eval.quality,
                attempts=primary_attempts + (failed,),
            )
        except Exception as error:
            failed = OCRAttempt(
                provider=getattr(self.fallback, "name", "fallback"),
                strategy=None,
                quality=POOR,
                character_count=0,
                word_count=0,
                confidence=None,
                score=0.0,
                error=f"{type(error).__name__}: {error}",
            )
            return _decorate(
                primary_result,
                quality=primary_eval.quality,
                attempts=primary_attempts + (failed,),
            )

        if fallback_eval.score > primary_eval.score:
            return _decorate(
                fallback_result,
                quality=fallback_eval.quality,
                attempts=primary_attempts + fallback_attempts,
            )

        return _decorate(
            primary_result,
            quality=primary_eval.quality,
            attempts=primary_attempts + fallback_attempts,
        )


def _decorate(result: OCRPageResult, *, quality: str, attempts: tuple[OCRAttempt, ...]) -> OCRPageResult:
    return OCRPageResult(
        text=result.text,
        confidence=result.confidence,
        words=tuple(result.words or ()),
        provider_name=result.provider_name,
        strategy=result.strategy,
        quality=quality,
        attempts=attempts,
    )

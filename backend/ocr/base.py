"""Provider-neutral OCR contracts for LifeOS Document Brain."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class OCRError(RuntimeError):
    """Base OCR failure exposed to the document workflow."""


class OCRConfigurationError(OCRError):
    """Raised when the configured OCR provider is unavailable or invalid."""


class OCRProviderError(OCRError):
    """Raised when an OCR provider cannot recognize a rendered page."""


@dataclass(frozen=True)
class OCRWord:
    """One OCR word positioned in normalized page coordinates."""

    text: str
    left: float
    top: float
    width: float
    height: float
    confidence: float | None = None


@dataclass(frozen=True)
class OCRAttempt:
    """One provider/strategy attempt considered for a rendered page.

    This audit record makes the adaptive OCR decision observable without
    leaking provider-specific objects into Document Brain workflows.
    """

    provider: str
    strategy: str | None
    quality: str
    character_count: int
    word_count: int
    confidence: float | None
    score: float
    error: str | None = None


@dataclass(frozen=True)
class OCRPageResult:
    """Recognized text and optional layout for one rendered PDF page."""

    text: str
    confidence: float | None = None
    words: tuple[OCRWord, ...] = ()
    provider_name: str | None = None
    strategy: str | None = None
    quality: str | None = None
    attempts: tuple[OCRAttempt, ...] = ()


class OCRProvider(ABC):
    """Small interface that keeps OCR vendors out of document workflows."""

    name: str

    @abstractmethod
    def recognize_page(
        self,
        image_bytes: bytes,
        *,
        page_number: int,
    ) -> OCRPageResult:
        """Recognize a single rendered page image."""

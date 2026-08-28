"""OCR provider implementations."""

from ocr.providers.adaptive import AdaptiveOCRProvider
from ocr.providers.easyocr import EasyOCRProvider
from ocr.providers.tesseract import TesseractOCRProvider

__all__ = ["AdaptiveOCRProvider", "EasyOCRProvider", "TesseractOCRProvider"]

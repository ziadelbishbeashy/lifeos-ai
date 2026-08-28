"""Step 15G adaptive OCR provider tests (no live OCR/model calls)."""

from io import BytesIO

from PIL import Image

from ocr.base import OCRPageResult, OCRProvider, OCRWord
from ocr.providers.adaptive import AdaptiveOCRProvider
from ocr.providers.easyocr import EasyOCRProvider
from ocr.providers.tesseract import TesseractOCRProvider


class StaticProvider(OCRProvider):
    def __init__(self, name: str, result: OCRPageResult):
        self.name = name
        self.result = result
        self.calls = 0

    def recognize_page(self, image_bytes: bytes, *, page_number: int):
        self.calls += 1
        return OCRPageResult(
            text=self.result.text,
            confidence=self.result.confidence,
            words=self.result.words,
            provider_name=self.name,
            strategy=self.result.strategy,
            quality=self.result.quality,
            attempts=self.result.attempts,
        )


def _text(words: int, token: str = "energy") -> str:
    return " ".join([token] * words)


def _png() -> bytes:
    image = Image.new("RGB", (1200, 1600), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_poor_tesseract_page_uses_better_easyocr_fallback():
    primary = StaticProvider(
        "tesseract",
        OCRPageResult(text="Lecture 5 title", confidence=0.78, strategy="psm_3"),
    )
    fallback = StaticProvider(
        "easyocr",
        OCRPageResult(text=_text(70, "potential-energy"), confidence=0.92, strategy="standard"),
    )
    adaptive = AdaptiveOCRProvider(primary=primary, fallback=fallback)

    result = adaptive.recognize_page(b"image", page_number=1)

    assert primary.calls == 1
    assert fallback.calls == 1
    assert result.provider_name == "easyocr"
    assert result.strategy == "standard"
    assert result.quality == "good"
    assert {attempt.provider for attempt in result.attempts} == {"tesseract", "easyocr"}


def test_acceptable_tesseract_page_skips_easyocr():
    primary = StaticProvider(
        "tesseract",
        OCRPageResult(text=_text(22, "mechanics"), confidence=0.88, strategy="psm_6"),
    )
    fallback = StaticProvider(
        "easyocr",
        OCRPageResult(text=_text(70), confidence=0.95, strategy="standard"),
    )
    adaptive = AdaptiveOCRProvider(primary=primary, fallback=fallback)

    result = adaptive.recognize_page(b"image", page_number=1)

    assert primary.calls == 1
    assert fallback.calls == 0
    assert result.provider_name == "tesseract"
    assert result.quality in {"acceptable", "good"}


def test_easyocr_is_not_selected_when_it_is_worse_than_tesseract():
    primary = StaticProvider(
        "tesseract",
        OCRPageResult(text="potential energy mechanics lecture text", confidence=0.72, strategy="psm_11"),
    )
    fallback = StaticProvider(
        "easyocr",
        OCRPageResult(text="x y", confidence=0.20, strategy="standard"),
    )
    adaptive = AdaptiveOCRProvider(primary=primary, fallback=fallback)

    result = adaptive.recognize_page(b"image", page_number=1)

    assert fallback.calls == 1
    assert result.provider_name == "tesseract"
    assert len(result.attempts) == 2


def test_tesseract_multi_pass_selects_best_psm(monkeypatch):
    import pytesseract

    def data_for(words: list[str], confidence: int):
        count = len(words)
        return {
            "text": words,
            "conf": [str(confidence)] * count,
            "left": [10 + i * 12 for i in range(count)],
            "top": [20] * count,
            "width": [10] * count,
            "height": [18] * count,
            "block_num": [1] * count,
            "par_num": [1] * count,
            "line_num": [1] * count,
        }

    def fake_image_to_data(image, *, lang, config, output_type):
        if config == "--psm 3":
            return data_for(["Lecture", "5", "title"], 80)
        if config == "--psm 6":
            return data_for(["potentialenergy"] * 45, 91)
        if config == "--psm 11":
            return data_for(["mechanics"] * 18, 84)
        raise AssertionError(config)

    monkeypatch.setattr(pytesseract, "image_to_data", fake_image_to_data)
    provider = TesseractOCRProvider(psm_modes=(3, 6, 11))

    result = provider.recognize_page(_png(), page_number=1)

    assert result.provider_name == "tesseract"
    assert result.strategy == "psm_6"
    assert result.quality == "good"
    assert len(result.attempts) == 2
    assert {attempt.strategy for attempt in result.attempts} == {"psm_3", "psm_6"}


def test_easyocr_provider_preserves_selectable_word_boxes():
    class FakeReader:
        def readtext(self, image, **kwargs):
            return [
                (
                    [[100, 200], [500, 200], [500, 260], [100, 260]],
                    "potential energy",
                    0.93,
                )
            ]

    provider = EasyOCRProvider(
        languages=("en",),
        reader_factory=lambda *args, **kwargs: FakeReader(),
    )
    result = provider.recognize_page(_png(), page_number=1)

    assert result.provider_name == "easyocr"
    assert result.text == "potential energy"
    assert [word.text for word in result.words] == ["potential", "energy"]
    assert all(0 <= word.left <= 1 for word in result.words)
    assert all(0 < word.width <= 1 for word in result.words)
    assert result.confidence == 0.93

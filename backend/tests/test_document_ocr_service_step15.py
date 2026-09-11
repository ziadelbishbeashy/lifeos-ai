"""Step 15 page-aware OCR extraction tests."""

from io import BytesIO

from ocr.base import OCRPageResult, OCRProvider, OCRWord
from services import document_ocr_service as service
from storage.local import LocalStorage


class FakePage:
    def __init__(self, text: str, *, images=()):
        self._text = text
        self.images = images

    def extract_text(self):
        return self._text


class FakeEmbeddedImage:
    def __init__(self, *, width: int, height: int):
        self.image = type("Image", (), {"width": width, "height": height})()


class FakeReader:
    is_encrypted = False

    def __init__(self, pages):
        self.pages = pages


class RecordingProvider(OCRProvider):
    name = "fake-ocr"

    def __init__(self):
        self.pages: list[int] = []

    def recognize_page(self, image_bytes: bytes, *, page_number: int):
        self.pages.append(page_number)
        return OCRPageResult(
            text=f"OCR recovered content for page {page_number}.",
            confidence=0.91 if page_number == 2 else 0.60,
            words=(
                OCRWord(
                    text="OCR",
                    left=0.1,
                    top=0.2,
                    width=0.08,
                    height=0.03,
                    confidence=0.91,
                ),
            ),
        )


def _stored_pdf(tmp_path):
    storage = LocalStorage(tmp_path)
    key = storage.save(
        BytesIO(b"%PDF-1.7\nplaceholder"),
        original_name="scan.pdf",
        namespace="ocr-tests",
    )
    return storage, key


def test_mixed_pdf_only_ocrs_pages_without_useful_native_text(monkeypatch, tmp_path):
    storage, key = _stored_pdf(tmp_path)
    reader = FakeReader(
        [
            FakePage("Native page one contains enough readable words."),
            FakePage(""),
            FakePage("Native page three also has readable content."),
        ]
    )
    monkeypatch.setattr(service, "PdfReader", lambda *args, **kwargs: reader)

    rendered: list[int] = []

    def render_page(pdf_bytes, *, page_index, dpi):
        rendered.append(page_index)
        return f"page-{page_index}".encode()

    provider = RecordingProvider()
    result = service.extract_stored_pdf_with_ocr(
        key,
        provider=provider,
        storage=storage,
        render_page=render_page,
    )

    assert rendered == [1]
    assert provider.pages == [2]
    assert result.page_count == 3
    assert result.native_page_count == 2
    assert result.ocr_page_count == 1
    assert result.pages_processed == 1
    assert result.pages[1].words[0].text == "OCR"
    assert "--- Page 1 ---" in result.text
    assert "--- Page 2 ---" in result.text
    assert "OCR recovered content for page 2." in result.text
    assert "--- Page 3 ---" in result.text


def test_low_confidence_ocr_is_counted_without_dropping_text(monkeypatch, tmp_path):
    storage, key = _stored_pdf(tmp_path)
    reader = FakeReader([FakePage(""), FakePage("")])
    monkeypatch.setattr(service, "PdfReader", lambda *args, **kwargs: reader)

    provider = RecordingProvider()
    result = service.extract_stored_pdf_with_ocr(
        key,
        provider=provider,
        storage=storage,
        render_page=lambda *args, **kwargs: b"png",
        low_confidence_threshold=0.70,
    )

    assert result.ocr_page_count == 2
    assert result.low_confidence_page_count == 1
    assert round(result.average_confidence or 0, 3) == 0.755
    assert "OCR recovered content for page 1." in result.text
    assert "OCR recovered content for page 2." in result.text


def test_native_text_heuristic_flags_empty_and_garbage_pages():
    from services.pdf_service import is_useful_native_page_text

    assert is_useful_native_page_text("") is False
    assert is_useful_native_page_text("x") is False
    assert is_useful_native_page_text("Project launch readiness plan") is True


def test_preprocessor_runs_before_provider(monkeypatch, tmp_path):
    storage, key = _stored_pdf(tmp_path)
    reader = FakeReader([FakePage("")])
    monkeypatch.setattr(service, "PdfReader", lambda *args, **kwargs: reader)

    received: list[bytes] = []

    class InspectingProvider(OCRProvider):
        name = "inspect"

        def recognize_page(self, image_bytes: bytes, *, page_number: int):
            received.append(image_bytes)
            return OCRPageResult(text="Recovered text from cleaned image.", confidence=0.9)

    result = service.extract_stored_pdf_with_ocr(
        key,
        provider=InspectingProvider(),
        storage=storage,
        render_page=lambda *args, **kwargs: b"raw-render",
        preprocess_image=lambda image_bytes: b"cleaned-" + image_bytes,
    )

    assert received == [b"cleaned-raw-render"]
    assert "Recovered text from cleaned image." in result.text


def test_thin_native_text_over_large_embedded_image_is_still_ocred(monkeypatch, tmp_path):
    storage, key = _stored_pdf(tmp_path)
    reader = FakeReader([
        FakePage(
            "Lecture 5",
            images=(FakeEmbeddedImage(width=1600, height=2200),),
        )
    ])
    monkeypatch.setattr(service, "PdfReader", lambda *args, **kwargs: reader)

    rendered: list[int] = []
    provider = RecordingProvider()
    result = service.extract_stored_pdf_with_ocr(
        key,
        provider=provider,
        storage=storage,
        render_page=lambda pdf_bytes, *, page_index, dpi: (
            rendered.append(page_index) or b"page-image"
        ),
    )

    assert rendered == [0]
    assert provider.pages == [1]
    assert result.ocr_page_count == 1
    assert result.native_page_count == 0
    assert result.pages[0].source == "ocr"
    assert result.pages[0].ocr_reason == "thin_native_text_over_image"
    assert "OCR recovered content for page 1." in result.text

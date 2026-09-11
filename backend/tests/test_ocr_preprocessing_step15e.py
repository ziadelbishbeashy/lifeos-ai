"""Step 15E.1 OpenCV preprocessing tests."""

from __future__ import annotations

import cv2
import numpy as np

from ocr.preprocessing import preprocess_ocr_image


def _png_bytes(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


def test_auto_preprocessing_keeps_a_valid_png_and_records_operations():
    # Deliberately low-contrast gray page with darker text-like blocks.
    image = np.full((240, 500, 3), 190, dtype=np.uint8)
    cv2.rectangle(image, (50, 70), (430, 82), (150, 150, 150), -1)
    cv2.rectangle(image, (70, 115), (380, 127), (145, 145, 145), -1)

    result = preprocess_ocr_image(_png_bytes(image), mode="auto")

    assert result.image_bytes.startswith(b"\x89PNG")
    assert "grayscale" in result.operations
    assert "clahe_contrast" in result.operations
    assert result.output_contrast >= 0


def test_document_mode_adds_black_white_thresholding():
    image = np.full((180, 400, 3), 235, dtype=np.uint8)
    cv2.putText(
        image,
        "LifeOS OCR",
        (40, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (40, 40, 40),
        2,
        cv2.LINE_AA,
    )

    result = preprocess_ocr_image(_png_bytes(image), mode="document")

    assert "otsu_threshold" in result.operations
    decoded = cv2.imdecode(np.frombuffer(result.image_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    assert decoded is not None
    assert set(np.unique(decoded)).issubset({0, 255})


def test_none_mode_leaves_bytes_untouched():
    image = np.full((30, 30, 3), 255, dtype=np.uint8)
    original = _png_bytes(image)

    result = preprocess_ocr_image(original, mode="none")

    assert result.image_bytes == original
    assert result.operations == ()

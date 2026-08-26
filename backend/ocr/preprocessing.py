"""Conservative OpenCV preprocessing for OCR page images.

This module does *not* recognize text. It only makes a rendered page easier for
OCR engines to read. The default ``auto`` mode is intentionally conservative:
- convert to grayscale,
- improve contrast only when the page is low contrast,
- deskew only when the estimated rotation is small and trustworthy.

The more aggressive ``document`` mode additionally produces a black/white
(Otsu-thresholded) page. This can help poor scans, but should not be the default
for every document because thresholding can damage already-good pages.
"""

from __future__ import annotations

from dataclasses import dataclass


class OCRPreprocessingError(RuntimeError):
    """Raised when an OCR image cannot be decoded or preprocessed safely."""


@dataclass(frozen=True)
class OCRPreprocessingResult:
    """Processed PNG bytes plus a small audit trail of applied operations."""

    image_bytes: bytes
    operations: tuple[str, ...]
    estimated_skew_degrees: float | None
    input_contrast: float
    output_contrast: float


def preprocess_ocr_image(
    image_bytes: bytes,
    *,
    mode: str = "auto",
) -> OCRPreprocessingResult:
    """Return a cleaned PNG image for OCR.

    Supported modes:
    - ``none``: keep the rendered image unchanged.
    - ``auto``: grayscale + conditional contrast normalization + safe deskew.
    - ``document``: ``auto`` plus Otsu black/white thresholding.

    The function is provider-neutral, so both Tesseract and future OCR engines
    can reuse the same preprocessing stage.
    """

    cleaned_mode = str(mode or "auto").strip().lower()
    if cleaned_mode not in {"none", "auto", "document"}:
        raise OCRPreprocessingError(
            f'Unsupported OCR preprocessing mode "{cleaned_mode}".'
        )
    if not image_bytes:
        raise OCRPreprocessingError("The OCR image is empty.")
    if cleaned_mode == "none":
        return OCRPreprocessingResult(
            image_bytes=image_bytes,
            operations=(),
            estimated_skew_degrees=None,
            input_contrast=0.0,
            output_contrast=0.0,
        )

    try:
        import cv2
        import numpy as np
    except ImportError as error:  # pragma: no cover - environment guard
        raise OCRPreprocessingError(
            "OpenCV preprocessing dependencies are not installed."
        ) from error

    encoded = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise OCRPreprocessingError("LifeOS could not decode the OCR page image.")

    operations: list[str] = []

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    operations.append("grayscale")
    input_contrast = float(gray.std())

    # Low-contrast scans benefit from local contrast normalization. On already
    # crisp pages, leaving the pixels alone avoids unnecessary transformation.
    working = gray
    if input_contrast < 55.0:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        working = clahe.apply(working)
        operations.append("clahe_contrast")

    estimated_skew = _estimate_skew_degrees(working, cv2=cv2, np=np)
    if estimated_skew is not None and 0.5 <= abs(estimated_skew) <= 5.0:
        working = _rotate_image(working, estimated_skew, cv2=cv2)
        operations.append("deskew")

    if cleaned_mode == "document":
        # Otsu chooses a page-specific threshold automatically. This is useful
        # for clearly scanned paperwork, but deliberately opt-in because it can
        # erase faint annotations or colored content.
        _, working = cv2.threshold(
            working,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU,
        )
        operations.append("otsu_threshold")

    success, output = cv2.imencode(".png", working)
    if not success:
        raise OCRPreprocessingError("LifeOS could not encode the cleaned OCR image.")

    return OCRPreprocessingResult(
        image_bytes=output.tobytes(),
        operations=tuple(operations),
        estimated_skew_degrees=estimated_skew,
        input_contrast=input_contrast,
        output_contrast=float(working.std()),
    )


def _estimate_skew_degrees(image, *, cv2, np) -> float | None:
    """Estimate small page rotation using the foreground text-like pixels."""

    # Invert so dark text becomes white foreground for geometry detection.
    _, binary = cv2.threshold(
        image,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )
    points = cv2.findNonZero(binary)
    if points is None or len(points) < 50:
        return None

    angle = float(cv2.minAreaRect(points)[-1])
    # OpenCV's minAreaRect angle convention differs around -45/90 degrees.
    if angle > 45.0:
        angle -= 90.0

    # We rotate by the opposite amount to straighten the page.
    correction = -angle
    if abs(correction) > 15.0:
        # Large rotations are likely page orientation/layout rather than simple
        # scanner skew. Orientation detection belongs in a later OCR stage.
        return None
    return correction


def _rotate_image(image, angle: float, *, cv2):
    height, width = image.shape[:2]
    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )

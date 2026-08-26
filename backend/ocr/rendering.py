"""PDF page rendering helpers used only when OCR is required."""

from __future__ import annotations


class OCRRenderError(RuntimeError):
    """Raised when a PDF page cannot be rendered for OCR."""


def render_pdf_page_png(
    pdf_bytes: bytes,
    *,
    page_index: int,
    dpi: int = 300,
) -> bytes:
    """Render one zero-based PDF page to PNG bytes with PyMuPDF.

    The import is intentionally lazy: normal text PDFs never need the renderer,
    so the OCR dependency stays outside the fast native-text path.
    """

    if not pdf_bytes:
        raise OCRRenderError("The stored PDF is empty.")
    if page_index < 0:
        raise ValueError("The PDF page index cannot be negative.")
    if dpi < 72:
        raise ValueError("OCR rendering DPI must be at least 72.")

    try:
        import pymupdf
    except ImportError as error:  # pragma: no cover - environment guard
        raise OCRRenderError(
            "PyMuPDF is not installed. Install backend OCR dependencies first."
        ) from error

    try:
        document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        try:
            if page_index >= document.page_count:
                raise OCRRenderError("The requested PDF page does not exist.")
            page = document.load_page(page_index)
            zoom = float(dpi) / 72.0
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            return pixmap.tobytes("png")
        finally:
            document.close()
    except OCRRenderError:
        raise
    except Exception as error:
        raise OCRRenderError("LifeOS could not render this PDF page for OCR.") from error

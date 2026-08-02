"""Tests for Document Brain PDF validation."""

from io import BytesIO

import pytest
from werkzeug.datastructures import FileStorage

from services.pdf_service import (
    PDFValidationError,
    validate_pdf_upload,
    store_pdf_upload,
)
from storage.local import LocalStorage

ONE_MEGABYTE = 1024 * 1024


def make_upload(
    content: bytes,
    filename: str,
) -> FileStorage:
    """Create a fake uploaded file for testing."""

    return FileStorage(
        stream=BytesIO(content),
        filename=filename,
        content_type="application/pdf",
    )


def test_valid_pdf_is_accepted():
    upload = make_upload(
        content=b"%PDF-1.7\nFake PDF test content",
        filename="LifeOS Requirements.pdf",
    )

    result = validate_pdf_upload(
        upload,
        max_bytes=ONE_MEGABYTE,
    )

    assert result.original_name == "LifeOS Requirements.pdf"
    assert result.safe_name == "LifeOS_Requirements.pdf"
    assert result.size_bytes == len(
        b"%PDF-1.7\nFake PDF test content"
    )

    # Validation must return the stream to the beginning so
    # the storage service can read the complete file later.
    assert upload.stream.tell() == 0


def test_missing_pdf_is_rejected():
    with pytest.raises(
        PDFValidationError,
        match="Please select a PDF file",
    ):
        validate_pdf_upload(
            None,
            max_bytes=ONE_MEGABYTE,
        )


def test_missing_filename_is_rejected():
    upload = make_upload(
        content=b"%PDF-1.7\nContent",
        filename="",
    )

    with pytest.raises(
        PDFValidationError,
        match="Please select a PDF file",
    ):
        validate_pdf_upload(
            upload,
            max_bytes=ONE_MEGABYTE,
        )


def test_non_pdf_extension_is_rejected():
    upload = make_upload(
        content=b"%PDF-1.7\nContent",
        filename="requirements.txt",
    )

    with pytest.raises(
        PDFValidationError,
        match="Only PDF files are supported",
    ):
        validate_pdf_upload(
            upload,
            max_bytes=ONE_MEGABYTE,
        )


def test_empty_pdf_is_rejected():
    upload = make_upload(
        content=b"",
        filename="empty.pdf",
    )

    with pytest.raises(
        PDFValidationError,
        match="uploaded PDF is empty",
    ):
        validate_pdf_upload(
            upload,
            max_bytes=ONE_MEGABYTE,
        )


def test_fake_pdf_is_rejected():
    upload = make_upload(
        content=b"This is not really a PDF file.",
        filename="fake.pdf",
    )

    with pytest.raises(
        PDFValidationError,
        match="does not appear to be a valid PDF",
    ):
        validate_pdf_upload(
            upload,
            max_bytes=ONE_MEGABYTE,
        )


def test_oversized_pdf_is_rejected():
    upload = make_upload(
        content=b"%PDF-" + (b"x" * 100),
        filename="large.pdf",
    )

    with pytest.raises(
        PDFValidationError,
        match="cannot exceed",
    ):
        validate_pdf_upload(
            upload,
            max_bytes=50,
        )


def test_uppercase_pdf_extension_is_accepted():
    upload = make_upload(
        content=b"%PDF-1.7\nContent",
        filename="REPORT.PDF",
    )

    result = validate_pdf_upload(
        upload,
        max_bytes=ONE_MEGABYTE,
    )

    assert result.safe_name == "REPORT.PDF"


def test_unsafe_filename_is_cleaned():
    upload = make_upload(
        content=b"%PDF-1.7\nContent",
        filename="../../private report.pdf",
    )

    result = validate_pdf_upload(
        upload,
        max_bytes=ONE_MEGABYTE,
    )

    assert result.original_name == "../../private report.pdf"
    assert result.safe_name == "private_report.pdf"


def test_invalid_maximum_size_is_rejected():
    upload = make_upload(
        content=b"%PDF-1.7\nContent",
        filename="report.pdf",
    )

    with pytest.raises(
        ValueError,
        match="maximum upload size must be positive",
    ):
        validate_pdf_upload(
            upload,
            max_bytes=0,
        )


def test_valid_pdf_is_stored_securely(tmp_path):
    upload = make_upload(
        content=b"%PDF-1.7\nLifeOS document content",
        filename="LifeOS Requirements.pdf",
    )

    storage = LocalStorage(tmp_path)

    result = store_pdf_upload(
        upload,
        owner_id=1,
        project_id=7,
        max_bytes=ONE_MEGABYTE,
        storage=storage,
    )

    assert result.original_name == (
        "LifeOS Requirements.pdf"
    )
    assert result.safe_name == (
        "LifeOS_Requirements.pdf"
    )
    assert result.size_bytes == len(
        b"%PDF-1.7\nLifeOS document content"
    )

    assert result.storage_key.startswith(
        "user-1-project-7/"
    )
    assert result.storage_key.endswith(
        "_LifeOS_Requirements.pdf"
    )

    assert storage.exists(result.storage_key)

    with storage.open(
        result.storage_key,
        "rb",
    ) as stored_file:
        assert stored_file.read() == (
            b"%PDF-1.7\nLifeOS document content"
        )

    assert upload.stream.tell() == 0
"""Step 15 OCR workflow/state/indexing tests."""

from types import SimpleNamespace

import pytest

from database import db
from models import Document, Project
from ocr.base import OCRProvider
from services.document_ocr_service import OCRDocumentExtraction, OCRPageExtraction
from services import document_ocr_workflow_service as workflow


class FakeProvider(OCRProvider):
    name = "fake-ocr"

    def recognize_page(self, image_bytes: bytes, *, page_number: int):  # pragma: no cover
        raise AssertionError("workflow test injects the extraction result")


def _document(user, *, status="pending", text="old native text"):
    project = Project(
        user_id=user,
        title="OCR Project",
        status="In Progress",
        priority="High",
    )
    db.session.add(project)
    db.session.flush()
    document = Document(
        project_id=project.id,
        filename="scan.pdf",
        file_path="user/scan.pdf",
        extracted_text=text,
        ocr_status=status,
        ocr_total_pages=2,
        ocr_pages_requested=1,
    )
    db.session.add(document)
    db.session.commit()
    return document


def _extraction():
    return OCRDocumentExtraction(
        text=(
            "--- Page 1 ---\nNative page.\n\n"
            "--- Page 2 ---\nRecovered scanned page."
        ),
        page_count=2,
        native_page_count=1,
        ocr_page_count=1,
        pages_processed=1,
        low_confidence_page_count=0,
        average_confidence=0.95,
        truncated=False,
        pages=(
            OCRPageExtraction(1, "Native page.", "native", None),
            OCRPageExtraction(2, "Recovered scanned page.", "ocr", 0.95),
        ),
    )


def test_processing_saves_ocr_text_then_reuses_existing_chunk_pipeline(
    app, user, monkeypatch
):
    with app.app_context():
        document = _document(user)
        monkeypatch.setattr(
            workflow,
            "extract_stored_pdf_with_ocr",
            lambda *args, **kwargs: _extraction(),
        )
        monkeypatch.setattr(
            workflow,
            "ensure_owned_document_chunks",
            lambda **kwargs: SimpleNamespace(chunks=["a", "b"]),
        )

        result = workflow.process_owned_document_ocr(
            document_id=document.id,
            user_id=user,
            provider=FakeProvider(),
        )

        saved = db.session.get(Document, document.id)
        assert saved.ocr_status == "completed"
        assert saved.ocr_provider == "fake-ocr"
        assert saved.ocr_total_pages == 2
        assert saved.ocr_pages_requested == 1
        assert saved.ocr_pages_processed == 1
        assert saved.ocr_average_confidence == pytest.approx(0.95)
        assert "Recovered scanned page" in saved.extracted_text
        assert result.indexing_succeeded is True
        assert result.chunk_count == 2


def test_ocr_failure_preserves_existing_text_and_sets_retryable_failed_state(
    app, user, monkeypatch
):
    with app.app_context():
        document = _document(user, text="keep this text")

        def fail(*args, **kwargs):
            from services.document_ocr_service import DocumentOCRError
            raise DocumentOCRError("OCR provider unavailable")

        monkeypatch.setattr(workflow, "extract_stored_pdf_with_ocr", fail)

        with pytest.raises(workflow.DocumentOCRWorkflowError):
            workflow.process_owned_document_ocr(
                document_id=document.id,
                user_id=user,
                provider=FakeProvider(),
            )

        saved = db.session.get(Document, document.id)
        assert saved.ocr_status == "failed"
        assert saved.ocr_error == "OCR provider unavailable"
        assert saved.extracted_text == "keep this text"


def test_queue_is_idempotent_while_job_is_active(app, user):
    from jobs.queue import MemoryJobQueue

    with app.app_context():
        document = _document(user)
        queue = MemoryJobQueue()

        first = workflow.queue_owned_document_ocr(
            document_id=document.id,
            user_id=user,
            queue=queue,
        )
        second = workflow.queue_owned_document_ocr(
            document_id=document.id,
            user_id=user,
            queue=queue,
        )

        assert first.queued is True
        assert first.job_id
        assert second.queued is False
        assert len(queue.jobs) == 1

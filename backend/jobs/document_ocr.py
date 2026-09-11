"""Document OCR job registration."""

from __future__ import annotations

from jobs.registry import register_job
from services.document_ocr_workflow_service import OCR_JOB_NAME, process_owned_document_ocr


def handle_document_ocr(payload: dict) -> None:
    process_owned_document_ocr(
        document_id=int(payload["document_id"]),
        user_id=int(payload["user_id"]),
        force=bool(payload.get("force", False)),
    )


def register_document_ocr_job() -> None:
    register_job(OCR_JOB_NAME, handle_document_ocr)

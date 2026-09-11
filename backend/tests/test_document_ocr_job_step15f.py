"""OCR job payload contract."""

from jobs import document_ocr as job_module


def test_job_handler_threads_force_into_authoritative_workflow(monkeypatch):
    captured = {}

    def fake_process(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(job_module, "process_owned_document_ocr", fake_process)

    job_module.handle_document_ocr({
        "document_id": 17,
        "user_id": 9,
        "force": True,
    })

    assert captured == {
        "document_id": 17,
        "user_id": 9,
        "force": True,
    }

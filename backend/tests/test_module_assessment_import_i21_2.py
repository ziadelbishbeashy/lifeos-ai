"""I21.2 intelligent academic schedule import regression tests.

The tests stub document ingestion/retrieval/reasoning so they exercise the
trust boundary and module distribution deterministically without external AI/OCR.
"""
from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from PIL import Image
from werkzeug.datastructures import FileStorage

from database import db
from models import Document, DocumentChunk, LifeOSActionProposal, ModuleAssessment
from services.module_assessment_service import create_owned_module_assessment
from services.module_service import create_module
import services.module_assessment_import_service as import_service


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "StrongPass123!"},
    )
    assert response.status_code == 200


def _modules(app, user_id: int) -> tuple[int, int]:
    with app.app_context():
        ml = create_module(user_id=user_id, title="Machine Learning", subject="Artificial Intelligence")
        os = create_module(user_id=user_id, title="Operating Systems", subject="Computer Engineering")
        return ml.id, os.id


def _stub_import_pipeline(monkeypatch, candidates):
    def fake_create_project_pdf_document(upload, *, owner_id, project_id=None, max_bytes, storage=None):
        document = Document(
            user_id=owner_id,
            project_id=project_id,
            filename="exam-timetable.pdf",
            file_path="tests/exam-timetable.pdf",
            extracted_text="FINAL EXAM TIMETABLE Machine Learning 2026-12-14 10:00 Operating Systems 2026-12-17 13:30",
            ocr_status="not_needed",
            is_current_version=True,
        )
        db.session.add(document)
        db.session.flush()
        chunk = DocumentChunk(
            document_id=document.id, user_id=owner_id, chunk_index=0, page_start=1, page_end=1,
            section_title="Final Exam Timetable", text=document.extracted_text,
            character_count=len(document.extracted_text), source_fingerprint="test-schedule-chunk",
        )
        db.session.add(chunk)
        db.session.commit()
        return SimpleNamespace(document=document)

    monkeypatch.setattr(import_service, "create_project_pdf_document", fake_create_project_pdf_document)
    monkeypatch.setattr(import_service, "_ensure_searchable", lambda uploaded, user_id: None)
    def fake_evidence_catalog(*, document_id, user_id):
        chunk = DocumentChunk.query.filter_by(document_id=document_id, user_id=user_id).one()
        return [{
            "id": "e1",
            "document_id": document_id,
            "chunk_id": chunk.id,
            "page": 1,
            "section": "Final Exam Timetable",
            "content_type": "text",
            "table_id": None,
            "excerpt": "Machine Learning 14/12/2026 10:00; Operating Systems 17/12/2026 13:30",
        }]

    monkeypatch.setattr(import_service, "_evidence_catalog", fake_evidence_catalog)
    monkeypatch.setattr(import_service, "extract_academic_schedule_items", lambda **kwargs: candidates)


def test_photo_schedule_is_normalized_to_pdf_for_existing_document_pipeline():
    raw = BytesIO()
    Image.new("RGB", (300, 120), "white").save(raw, format="PNG")
    raw.seek(0)
    upload = FileStorage(stream=raw, filename="exam schedule.png", content_type="image/png")

    prepared, original_name = import_service._prepare_upload(upload, max_bytes=2_000_000)

    assert original_name == "exam_schedule.png"
    assert prepared.filename == "exam_schedule-schedule-import.pdf"
    assert prepared.content_type == "application/pdf"
    assert prepared.stream.read(4) == b"%PDF"


def test_one_schedule_creates_pending_proposals_then_distributes_on_confirmation(app, client, user, monkeypatch):
    _login(client)
    ml_id, os_id = _modules(app, user)
    _stub_import_pipeline(
        monkeypatch,
        [
            {
                "title": "Final Exam",
                "assessment_type": "Final",
                "module_text": "CEN302 Machine Learning",
                "module_id": ml_id,
                "module_match_confidence": "high",
                "assessment_date": "2026-12-14",
                "assessment_time": "10:00",
                "due_date": None,
                "due_time": None,
                "weight_percent": None,
                "topics": None,
                "notes": None,
                "confidence": "high",
                "evidence_ids": ["e1"],
            },
            {
                "title": "Final Exam",
                "assessment_type": "Final",
                "module_text": "Operating System",
                "module_id": os_id,
                "module_match_confidence": "high",
                "assessment_date": "2026-12-17",
                "assessment_time": "13:30",
                "due_date": None,
                "due_time": None,
                "weight_percent": None,
                "topics": None,
                "notes": None,
                "confidence": "high",
                "evidence_ids": ["e1"],
            },
        ],
    )

    response = client.post(
        "/api/v1/modules/assessment-imports",
        data={"document": (BytesIO(b"%PDF-1.4 fake"), "finals.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    body = response.get_json()
    assert len(body["proposals"]) == 2
    proposal_ids = [row["id"] for row in body["proposals"]]
    assert {row["payload"]["module_id"] for row in body["proposals"]} == {ml_id, os_id}
    assert all(row["status"] == "pending" for row in body["proposals"])
    assert all(row["evidence"] and row["evidence"][0]["document_id"] == body["document"]["id"] for row in body["proposals"])

    with app.app_context():
        # Extraction is proposal-only. It must not create accepted workspace truth.
        assert ModuleAssessment.query.count() == 0

    confirmed = client.post(
        "/api/v1/modules/assessment-proposals/confirm-selected",
        json={"proposal_ids": proposal_ids},
    )
    assert confirmed.status_code == 200
    confirmed_body = confirmed.get_json()
    assert len(confirmed_body["confirmed"]) == 2
    assert confirmed_body["failed"] == []

    with app.app_context():
        rows = ModuleAssessment.query.order_by(ModuleAssessment.assessment_date.asc()).all()
        assert [(row.module_id, row.assessment_date.isoformat(), row.assessment_time.strftime("%H:%M")) for row in rows] == [
            (ml_id, "2026-12-14", "10:00"),
            (os_id, "2026-12-17", "13:30"),
        ]
        proposals = LifeOSActionProposal.query.filter(LifeOSActionProposal.id.in_(proposal_ids)).all()
        assert all(row.status == "confirmed" for row in proposals)
        assert all(row.execution_resource_type == "module_assessment" for row in proposals)


def test_unmatched_module_stays_reviewable_and_can_be_assigned_before_confirmation(app, client, user, monkeypatch):
    _login(client)
    ml_id, _ = _modules(app, user)
    _stub_import_pipeline(
        monkeypatch,
        [{
            "title": "Final Exam", "assessment_type": "Final", "module_text": "Engineering Mathematics",
            "module_id": None, "module_match_confidence": "low", "assessment_date": "2026-12-20", "assessment_time": "09:00",
            "due_date": None, "due_time": None, "weight_percent": 50, "topics": None, "notes": None,
            "confidence": "high", "evidence_ids": ["e1"],
        }],
    )

    imported = client.post(
        "/api/v1/modules/assessment-imports",
        data={"document": (BytesIO(b"%PDF-1.4 fake"), "finals.pdf")},
        content_type="multipart/form-data",
    )
    proposal = imported.get_json()["proposals"][0]
    assert proposal["payload"]["module_id"] is None
    assert proposal["payload"]["review_state"] == "needs_module"

    blocked = client.post(
        "/api/v1/modules/assessment-proposals/confirm-selected",
        json={"proposal_ids": [proposal["id"]]},
    ).get_json()
    assert blocked["confirmed"] == []
    assert blocked["failed"]
    with app.app_context():
        assert db.session.get(LifeOSActionProposal, proposal["id"]).status == "pending"
        assert ModuleAssessment.query.count() == 0

    updated = client.patch(
        f'/api/v1/modules/assessment-proposals/{proposal["id"]}',
        json={"module_id": ml_id},
    )
    assert updated.status_code == 200
    assert updated.get_json()["proposal"]["payload"]["module_id"] == ml_id

    confirmed = client.post(
        "/api/v1/modules/assessment-proposals/confirm-selected",
        json={"proposal_ids": [proposal["id"]]},
    ).get_json()
    assert len(confirmed["confirmed"]) == 1
    with app.app_context():
        assert ModuleAssessment.query.filter_by(module_id=ml_id).one().title == "Final Exam"


def test_duplicate_is_flagged_and_confirmation_does_not_fail_or_duplicate_workspace_truth(app, client, user, monkeypatch):
    _login(client)
    ml_id, _ = _modules(app, user)
    with app.app_context():
        create_owned_module_assessment(
            module_id=ml_id,
            user_id=user,
            title="Final Exam",
            assessment_type="Final",
            assessment_date="2026-12-14",
            assessment_time="10:00",
        )

    _stub_import_pipeline(
        monkeypatch,
        [{
            "title": "Final Exam", "assessment_type": "Final", "module_text": "Machine Learning",
            "module_id": ml_id, "module_match_confidence": "high", "assessment_date": "2026-12-14", "assessment_time": "10:00",
            "due_date": None, "due_time": None, "weight_percent": None, "topics": None, "notes": None,
            "confidence": "high", "evidence_ids": ["e1"],
        }],
    )
    imported = client.post(
        "/api/v1/modules/assessment-imports",
        data={"document": (BytesIO(b"%PDF-1.4 fake"), "finals.pdf")},
        content_type="multipart/form-data",
    ).get_json()
    proposal = imported["proposals"][0]
    assert proposal["payload"]["review_state"] == "possible_duplicate"
    assert proposal["payload"]["duplicate_assessment_id"] is not None

    result = client.post(
        "/api/v1/modules/assessment-proposals/confirm-selected",
        json={"proposal_ids": [proposal["id"]]},
    ).get_json()
    assert result["confirmed"] == []
    assert result["failed"]
    with app.app_context():
        assert ModuleAssessment.query.filter_by(module_id=ml_id).count() == 1
        # Prevalidation happens before I9 locks the row, so user can still edit/dismiss it.
        assert db.session.get(LifeOSActionProposal, proposal["id"]).status == "pending"

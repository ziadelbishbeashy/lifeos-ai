"""Step 15 OCR JSON API contracts."""

from database import db
from models import Document, Project, User


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "StrongPass123!"},
    )
    assert response.status_code == 200


def _document(user, *, status="pending"):
    project = Project(
        user_id=user,
        title="OCR API Project",
        status="In Progress",
        priority="High",
    )
    db.session.add(project)
    db.session.flush()
    document = Document(
        project_id=project.id,
        filename="scanned.pdf",
        file_path="scanned.pdf",
        ocr_status=status,
        ocr_total_pages=8,
        ocr_pages_requested=3,
        ocr_pages_processed=0,
    )
    db.session.add(document)
    db.session.commit()
    return document


def test_document_details_exposes_product_level_ocr_status(app, client, user):
    with app.app_context():
        document = _document(user)
        document_id = document.id

    _login(client)
    response = client.get(f"/api/v1/documents/{document_id}")

    assert response.status_code == 200
    ocr = response.get_json()["document"]["ocr"]
    assert ocr["status"] == "pending"
    assert ocr["needed"] is True
    assert ocr["total_pages"] == 8
    assert ocr["pages_requested"] == 3
    assert "provider" not in ocr


def test_ocr_start_queues_owned_document_without_blocking_testing_request(
    app, client, user
):
    with app.app_context():
        document = _document(user)
        document_id = document.id

    _login(client)
    response = client.post(f"/api/v1/documents/{document_id}/ocr", json={})

    assert response.status_code == 202
    payload = response.get_json()
    assert payload["queued"] is True
    assert payload["job_id"]
    assert payload["ocr"]["status"] == "queued"


def test_ocr_endpoint_does_not_expose_another_users_document(app, client, user):
    with app.app_context():
        other = User(name="Other", email="other-ocr@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()
        document = _document(other.id)
        document_id = document.id

    _login(client)
    response = client.get(f"/api/v1/documents/{document_id}/ocr")
    assert response.status_code == 404


def test_ocr_layout_endpoint_returns_owned_page_words(app, client, user):
    import json

    with app.app_context():
        document = _document(user, status="completed")
        document.ocr_layout_json = json.dumps({
            "version": 1,
            "pages": {
                "2": {
                    "page": 2,
                    "source": "ocr",
                    "confidence": 0.93,
                    "text": "Selectable OCR text",
                    "words": [
                        {
                            "text": "Selectable",
                            "left": 0.1,
                            "top": 0.2,
                            "width": 0.2,
                            "height": 0.05,
                            "confidence": 0.94,
                        }
                    ],
                }
            },
        })
        db.session.commit()
        document_id = document.id

    _login(client)
    response = client.get(f"/api/v1/documents/{document_id}/ocr/layout?page=2")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["layout_available"] is True
    assert payload["source"] == "ocr"
    assert payload["page"] == 2
    assert payload["words"][0]["text"] == "Selectable"


def test_ocr_status_reports_layout_availability(app, client, user):
    with app.app_context():
        document = _document(user, status="completed")
        document.ocr_layout_json = '{"version":1,"pages":{}}'
        db.session.commit()
        document_id = document.id

    _login(client)
    response = client.get(f"/api/v1/documents/{document_id}/ocr")

    assert response.status_code == 200
    assert response.get_json()["ocr"]["layout_available"] is True

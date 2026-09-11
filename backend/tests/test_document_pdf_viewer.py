"""Step 8B tests for the full PDF modal and protected download route."""

from __future__ import annotations

from io import BytesIO

from database import db
from models import Document, Project
from storage.local import LocalStorage


def login(client):
    return client.post(
        "/login",
        data={
            "email": "student@example.com",
            "password": "StrongPass123!",
        },
        follow_redirects=True,
    )


def create_pdf_document(app, user_id, tmp_path):
    app.config["LOCAL_STORAGE_ROOT"] = str(tmp_path)
    storage = LocalStorage(tmp_path)
    storage_key = storage.save(
        BytesIO(b"%PDF-1.4\n% Step 8B PDF\n"),
        original_name="viewer.pdf",
        namespace=f"user-{user_id}",
    )

    project = Project(
        user_id=user_id,
        title="PDF Viewer Project",
        status="In Progress",
        priority="Medium",
    )
    document = Document(
        project=project,
        filename="viewer.pdf",
        file_path=storage_key,
        extracted_text="--- Page 1 ---\nReadable PDF text.",
    )
    db.session.add_all([project, document])
    db.session.commit()
    return document.id


def test_document_details_contains_full_pdf_modal(app, client, user, tmp_path):
    with app.app_context():
        document_id = create_pdf_document(app, user, tmp_path)

    login(client)
    response = client.get(f"/documents/{document_id}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'data-db-pdf-modal' in html
    assert 'data-db-pdf-thumbnails' in html
    assert 'data-db-pdf-find-form' in html
    assert 'data-db-pdf-rotate-left' in html
    assert 'data-db-pdf-rotate-right' in html
    assert 'data-db-pdf-print' in html
    assert 'data-db-pdf-download' in html
    assert 'data-db-pdf-new-tab' in html
    assert 'document-pdf-viewer.js' in html


def test_pdf_download_mode_returns_attachment(app, client, user, tmp_path):
    with app.app_context():
        document_id = create_pdf_document(app, user, tmp_path)

    login(client)
    response = client.get(f"/documents/{document_id}/file?download=1")

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    disposition = response.headers.get("Content-Disposition", "")
    assert "attachment" in disposition.lower()
    assert "viewer.pdf" in disposition


def test_normal_pdf_route_remains_inline(app, client, user, tmp_path):
    with app.app_context():
        document_id = create_pdf_document(app, user, tmp_path)

    login(client)
    response = client.get(f"/documents/{document_id}/file")

    assert response.status_code == 200
    disposition = response.headers.get("Content-Disposition", "")
    assert "inline" in disposition.lower()
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"

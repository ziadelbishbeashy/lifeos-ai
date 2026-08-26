"""Regression coverage for the React Document Brain inline PDF endpoint."""

from io import BytesIO

from database import db
from models import Document, Project
from storage.local import LocalStorage


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "StrongPass123!"},
    )
    assert response.status_code == 200


def test_api_document_file_can_render_same_origin_iframe(app, client, user, tmp_path):
    with app.app_context():
        app.config["LOCAL_STORAGE_ROOT"] = str(tmp_path)
        storage = LocalStorage(tmp_path)
        storage_key = storage.save(
            BytesIO(b"%PDF-1.4\n% LifeOS inline viewer regression\n"),
            original_name="inline-viewer.pdf",
            namespace=f"user-{user}",
        )
        project = Project(user_id=user, title="Inline PDF Viewer")
        document = Document(
            project=project,
            filename="inline-viewer.pdf",
            file_path=storage_key,
            extracted_text="Inline viewer evidence.",
        )
        db.session.add_all([project, document])
        db.session.commit()
        document_id = document.id

    _login(client)
    response = client.get(f"/api/v1/documents/{document_id}/file")

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "no-store" in response.headers["Cache-Control"]

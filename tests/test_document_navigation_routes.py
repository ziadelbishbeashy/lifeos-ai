"""Route tests for Step 8A protected PDF and context endpoints."""

from __future__ import annotations

from io import BytesIO

from database import db
from models import (
    Document,
    DocumentChunk,
    Project,
)
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


def create_navigation_document(
    *,
    app,
    user_id: int,
    storage_root,
) -> tuple[int, int]:
    app.config["LOCAL_STORAGE_ROOT"] = str(
        storage_root
    )

    storage = LocalStorage(
        storage_root
    )

    storage_key = storage.save(
        BytesIO(
            b"%PDF-1.4\n% protected LifeOS document\n"
        ),
        original_name="navigation.pdf",
        namespace=f"user-{user_id}",
    )

    project = Project(
        user_id=user_id,
        title="Navigation Route Project",
        status="In Progress",
        priority="Medium",
    )

    document = Document(
        project=project,
        filename="navigation.pdf",
        file_path=storage_key,
        extracted_text="Readable document content.",
    )

    db.session.add_all(
        [
            project,
            document,
        ]
    )
    db.session.flush()

    chunk = DocumentChunk(
        document_id=document.id,
        user_id=user_id,
        chunk_index=3,
        page_start=8,
        page_end=8,
        section_title="Privacy",
        text="Private records stay inside the owned project.",
        character_count=46,
        source_fingerprint="fingerprint",
    )

    db.session.add(
        chunk
    )
    db.session.commit()

    return (
        document.id,
        chunk.id,
    )


def test_context_endpoint_returns_trusted_source_context(
    app,
    client,
    user,
    tmp_path,
):
    with app.app_context():
        document_id, chunk_id = create_navigation_document(
            app=app,
            user_id=user,
            storage_root=tmp_path,
        )

    login(
        client
    )

    response = client.get(
        f"/documents/{document_id}/context/{chunk_id}"
    )

    assert response.status_code == 200

    payload = response.get_json()

    assert payload["ok"] is True
    assert payload["document_id"] == document_id
    assert payload["current"]["chunk_id"] == chunk_id
    assert payload["current"]["page_label"] == "8"
    assert payload["current"]["section"] == "Privacy"
    assert payload["previous"] is None
    assert payload["next"] is None


def test_pdf_endpoint_serves_owned_pdf_inline(
    app,
    client,
    user,
    tmp_path,
):
    with app.app_context():
        document_id, _ = create_navigation_document(
            app=app,
            user_id=user,
            storage_root=tmp_path,
        )

    login(
        client
    )

    response = client.get(
        f"/documents/{document_id}/file"
    )

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(
        b"%PDF-1.4"
    )

    assert (
        response.headers["X-Frame-Options"]
        == "SAMEORIGIN"
    )

    assert "no-store" in response.headers[
        "Cache-Control"
    ]


def test_navigation_endpoints_require_login(
    app,
    client,
    user,
    tmp_path,
):
    with app.app_context():
        document_id, chunk_id = create_navigation_document(
            app=app,
            user_id=user,
            storage_root=tmp_path,
        )

    file_response = client.get(
        f"/documents/{document_id}/file"
    )

    context_response = client.get(
        f"/documents/{document_id}/context/{chunk_id}"
    )

    assert file_response.status_code in {
        302,
        401,
    }

    assert context_response.status_code in {
        302,
        401,
    }

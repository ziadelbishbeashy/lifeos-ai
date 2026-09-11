"""Step 14 document-version web route tests."""

from types import SimpleNamespace
from io import BytesIO

from database import db
from models import Document, DocumentVersionFamily, Project
from routes import document_routes


def _login(client):
    return client.post(
        "/login",
        data={
            "email": "student@example.com",
            "password": "StrongPass123!",
        },
        follow_redirects=False,
    )


def _versioned_documents(user):
    project = Project(user_id=user, title="Versioned")
    db.session.add(project)
    db.session.flush()

    family = DocumentVersionFamily(
        project_id=project.id,
        user_id=user,
        name="Requirements",
    )
    db.session.add(family)
    db.session.flush()

    old = Document(
        project=project,
        version_family=family,
        version_number=1,
        is_current_version=False,
        filename="requirements-v1.pdf",
        file_path="v1.pdf",
        extracted_text="Old",
    )
    current = Document(
        project=project,
        version_family=family,
        version_number=2,
        is_current_version=True,
        filename="requirements-v2.pdf",
        file_path="v2.pdf",
        extracted_text="Current",
    )
    db.session.add_all([old, current])
    db.session.commit()
    return old, current


def test_current_document_details_show_version_history(app, client, user):
    with app.app_context():
        old, current = _versioned_documents(user)
        current_id = current.id
        old_name = old.filename
        current_name = current.filename

    _login(client)

    response = client.get(
        f"/documents/{current_id}"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Document versioning" in html
    assert "Upload new version" in html
    assert old_name in html
    assert current_name in html
    assert "Compare with current" in html


def test_historical_type_detection_redirects_to_current_without_ai(
    app,
    client,
    user,
    monkeypatch,
):
    with app.app_context():
        old, current = _versioned_documents(user)
        old_id = old.id
        current_id = current.id

    monkeypatch.setattr(
        document_routes,
        "detect_owned_document_type",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("Historical version must not call type detection.")
        ),
    )

    _login(client)

    response = client.post(
        f"/documents/{old_id}/detect-type",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/documents/{current_id}"
    )


def test_upload_new_version_route_redirects_to_new_current(
    app,
    client,
    user,
    monkeypatch,
):
    with app.app_context():
        project = Project(user_id=user, title="Versioned")
        source = Document(
            project=project,
            filename="requirements.pdf",
            file_path="old.pdf",
            extracted_text="Old",
        )
        new_document = Document(
            project=project,
            filename="requirements-v2.pdf",
            file_path="new.pdf",
            extracted_text="New",
            version_number=2,
            is_current_version=True,
        )
        db.session.add_all([project, source, new_document])
        db.session.commit()
        source_id = source.id
        new_id = new_document.id

    monkeypatch.setattr(
        document_routes,
        "create_new_document_version",
        lambda *args, **kwargs: SimpleNamespace(
            current_document=SimpleNamespace(
                id=new_id,
                filename="requirements-v2.pdf",
                version_label="Version 2",
            ),
            change_summary={
                "changed_page_count": 1,
                "added_page_count": 0,
                "removed_page_count": 0,
                "content_changed": True,
            },
            upload_result=SimpleNamespace(
                extraction_succeeded=True,
                pages_with_text=1,
            ),
            embedding_message=None,
            embeddings_succeeded=True,
        ),
    )

    _login(client)

    response = client.post(
        f"/documents/{source_id}/versions",
        data={"document": (BytesIO(b"fake"), "requirements-v2.pdf")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/documents/{new_id}"
    )

"""Step 17 — user-owned document collections."""

from database import db
from models import Document, Project, User


def _login(client, email="student@example.com", password="StrongPass123!"):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200


def _document(user_id: int, *, title="Collection Project", filename="one.pdf") -> Document:
    project = Project(
        user_id=user_id,
        title=title,
        status="In Progress",
        priority="High",
    )
    document = Document(
        project=project,
        filename=filename,
        file_path=f"stored/{filename}",
        extracted_text="--- Page 1 ---\nA grounded collection test document.",
    )
    db.session.add_all([project, document])
    db.session.commit()
    return document


def test_collection_create_add_and_remove_document(app, client, user):
    with app.app_context():
        document_id = _document(user).id

    _login(client)

    created = client.post(
        "/api/v1/document-collections",
        json={"name": "Research Pack", "description": "Documents to study together."},
    )
    assert created.status_code == 201
    collection = created.get_json()["item"]
    collection_id = collection["id"]
    assert collection["document_count"] == 0

    added = client.post(
        f"/api/v1/document-collections/{collection_id}/documents",
        json={"document_id": document_id},
    )
    assert added.status_code == 200
    payload = added.get_json()["item"]
    assert payload["document_count"] == 1
    assert payload["documents"][0]["id"] == document_id

    details = client.get(f"/api/v1/document-collections/{collection_id}")
    assert details.status_code == 200
    assert details.get_json()["item"]["documents"][0]["filename"] == "one.pdf"

    removed = client.delete(
        f"/api/v1/document-collections/{collection_id}/documents/{document_id}"
    )
    assert removed.status_code == 200
    assert removed.get_json()["item"]["document_count"] == 0


def test_collection_cannot_add_another_users_document(app, client, user):
    with app.app_context():
        stranger = User(name="Other User", email="other@example.com")
        stranger.set_password("OtherPass123!")
        db.session.add(stranger)
        db.session.commit()
        foreign_document_id = _document(
            stranger.id,
            title="Other Project",
            filename="private.pdf",
        ).id

    _login(client)
    created = client.post("/api/v1/document-collections", json={"name": "Mine"})
    collection_id = created.get_json()["item"]["id"]

    response = client.post(
        f"/api/v1/document-collections/{collection_id}/documents",
        json={"document_id": foreign_document_id},
    )
    assert response.status_code == 404


def test_collection_listing_is_user_scoped(app, client, user):
    _login(client)
    client.post("/api/v1/document-collections", json={"name": "My Pack"})

    with app.app_context():
        stranger = User(name="Other User", email="other2@example.com")
        stranger.set_password("OtherPass123!")
        db.session.add(stranger)
        db.session.commit()
        from models import DocumentCollection
        db.session.add(DocumentCollection(user_id=stranger.id, name="Private Pack"))
        db.session.commit()

    response = client.get("/api/v1/document-collections")
    assert response.status_code == 200
    names = [item["name"] for item in response.get_json()["items"]]
    assert names == ["My Pack"]

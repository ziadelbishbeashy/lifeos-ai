"""Notes routes, ownership, and isolation tests."""

from database import db
from models import Note, Project, User


def _log_in(client, email="student@example.com", password="StrongPass123!"):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def _create_other_user_note(app):
    with app.app_context():
        other = User(name="Other Student", email="other-notes@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.flush()
        note = Note(
            user_id=other.id,
            title="Private other note",
            content="This must remain private.",
            note_type="Quick Note",
        )
        db.session.add(note)
        db.session.commit()
        return note.id


def test_notes_require_login(client):
    response = client.get("/notes/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_user_can_create_and_edit_note(client, app, user):
    _log_in(client)
    response = client.post(
        "/notes/create",
        data={
            "title": "Database lecture",
            "content": "Review normalization and SQL joins.",
            "note_type": "Lecture Note",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        note = Note.query.filter_by(title="Database lecture").one()
        note_id = note.id
        assert note.user_id == user

    edit_response = client.post(
        f"/notes/{note_id}/edit",
        data={
            "title": "Updated database lecture",
            "content": "Review normalization, SQL joins, and indexing.",
            "note_type": "Lecture Note",
        },
        follow_redirects=False,
    )
    assert edit_response.status_code == 302

    with app.app_context():
        assert db.session.get(Note, note_id).title == "Updated database lecture"


def test_note_routes_hide_another_users_note(client, app, user):
    other_note_id = _create_other_user_note(app)
    _log_in(client)

    assert client.get(f"/notes/{other_note_id}").status_code == 404
    assert client.get(f"/notes/{other_note_id}/edit").status_code == 404
    assert client.post(f"/notes/{other_note_id}/pin").status_code == 404
    assert client.post(f"/notes/{other_note_id}/delete").status_code == 404

    with app.app_context():
        assert db.session.get(Note, other_note_id) is not None


def test_note_cannot_link_to_another_users_project(client, app, user):
    with app.app_context():
        other = User(name="Other", email="other-project@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.flush()
        project = Project(
            user_id=other.id,
            title="Private project",
            status="In Progress",
            priority="Medium",
        )
        db.session.add(project)
        db.session.commit()
        project_id = project.id

    _log_in(client)
    response = client.post(
        "/notes/create",
        data={
            "title": "Invalid link",
            "content": "Should not connect to another user.",
            "note_type": "Project Note",
            "project_id": str(project_id),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"does not belong to your workspace" in response.data

    with app.app_context():
        assert Note.query.filter_by(user_id=user, title="Invalid link").count() == 0

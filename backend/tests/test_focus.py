"""Focus Mode route tests."""

from database import db
from models import FocusSession, User


def _log_in(client, email="student@example.com", password="StrongPass123!"):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def test_focus_requires_login(client):
    response = client.get("/focus/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_user_can_start_pause_and_cancel_focus(client, app, user):
    _log_in(client)
    start = client.post(
        "/focus/start",
        data={"duration_minutes": "25", "goal": "Finish one section"},
        follow_redirects=False,
    )
    assert start.status_code == 302

    with app.app_context():
        session = FocusSession.query.filter_by(user_id=user).one()
        session_id = session.id
        assert session.status == "running"

    pause = client.post(f"/focus/{session_id}/pause")
    assert pause.status_code == 200
    assert pause.get_json()["status"] == "paused"

    cancel = client.post(
        f"/focus/{session_id}/cancel",
        follow_redirects=False,
    )
    assert cancel.status_code == 302

    with app.app_context():
        assert db.session.get(FocusSession, session_id).status == "cancelled"


def test_focus_routes_hide_another_users_session(client, app, user):
    with app.app_context():
        other = User(name="Other", email="other-focus@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.flush()
        session = FocusSession(
            user_id=other.id,
            title="Private session",
            planned_minutes=25,
            status="paused",
        )
        db.session.add(session)
        db.session.commit()
        session_id = session.id

    _log_in(client)
    assert client.post(f"/focus/{session_id}/pause").status_code == 404

"""Native React Focus Studio API parity tests.

These contracts protect the original Focus Mode workflow while the UI lives
entirely in frontend/.  The API must continue to expose every state transition
needed by the React session experience.
"""

from database import db
from models import Task


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "StrongPass123!"},
    )
    assert response.status_code == 200


def test_native_focus_session_full_workflow_and_insights(app, client, user):
    with app.app_context():
        task = Task(
            user_id=user,
            title="Protect the focus workflow",
            importance="High",
            difficulty="Medium",
            status="Pending",
            priority_score=10,
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id

    _login(client)

    initial = client.get("/api/v1/focus")
    assert initial.status_code == 200
    assert initial.get_json()["active_session"] is None

    started = client.post(
        "/api/v1/focus/start",
        json={"task_id": task_id, "duration": 25, "goal": "Restore Focus Studio parity"},
    )
    assert started.status_code == 201
    session = started.get_json()["session"]
    session_id = session["id"]
    assert session["status"] == "running"
    assert session["task"]["title"] == "Protect the focus workflow"

    paused = client.post(f"/api/v1/focus/{session_id}/pause")
    assert paused.status_code == 200
    assert paused.get_json()["session"]["status"] == "paused"

    resumed = client.post(f"/api/v1/focus/{session_id}/resume")
    assert resumed.status_code == 200
    assert resumed.get_json()["session"]["status"] == "running"

    extended = client.post(f"/api/v1/focus/{session_id}/extend")
    assert extended.status_code == 200
    assert extended.get_json()["session"]["planned_minutes"] == 30

    parked = client.post(
        f"/api/v1/focus/{session_id}/distractions",
        json={"content": "Reply to the message later"},
    )
    assert parked.status_code == 201
    distraction_id = parked.get_json()["item"]["id"]

    converted = client.post(f"/api/v1/focus/distractions/{distraction_id}/convert")
    assert converted.status_code == 200
    assert converted.get_json()["task"]["title"] == "Reply to the message later"

    review = client.post(f"/api/v1/focus/{session_id}/review")
    assert review.status_code == 200
    assert review.get_json()["review_requested"] is True
    assert review.get_json()["session"]["status"] == "paused"

    finished = client.post(
        f"/api/v1/focus/{session_id}/finish",
        json={
            "goal_result": "full",
            "focus_rating": 5,
            "notes": "Focus Studio parity restored.",
            "complete_task": True,
        },
    )
    assert finished.status_code == 200
    completed = finished.get_json()["session"]
    assert completed["status"] == "completed"
    assert completed["goal_result"] == "full"
    assert completed["focus_rating"] == 5
    assert completed["notes"] == "Focus Studio parity restored."

    with app.app_context():
        assert db.session.get(Task, task_id).status == "Completed"

    state = client.get("/api/v1/focus").get_json()
    assert state["active_session"] is None

    insights = client.get("/api/v1/focus/insights")
    assert insights.status_code == 200
    payload = insights.get_json()
    assert payload["week_sessions"] == 1
    assert payload["average_rating"] == 5.0
    assert payload["week_distractions"] == 1
    assert payload["recent_sessions"][0]["id"] == session_id
    assert payload["recent_sessions"][0]["title"] == "Protect the focus workflow"

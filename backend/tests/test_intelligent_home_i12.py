from __future__ import annotations

from datetime import date, datetime, timedelta

from database import db
from models import Project, Task, User
from services.home_intelligence_service import build_owned_home_intelligence


def _project(user_id: int, title: str) -> Project:
    project = Project(
        user_id=user_id,
        title=title,
        status="In Progress",
        priority="Medium",
        progress=25,
    )
    db.session.add(project)
    db.session.commit()
    return project


def _login(client):
    return client.post(
        "/login",
        data={"email": "student@example.com", "password": "StrongPass123!"},
        follow_redirects=False,
    )


def test_i12_home_aggregates_verified_focus_deadlines_and_activity_without_writes(app, user):
    with app.app_context():
        project = _project(user, "LifeOS")
        blocked = Task(
            user_id=user,
            project_id=project.id,
            title="Fix blocker",
            status="Blocked",
            importance="High",
            created_at=datetime.utcnow(),
        )
        due = Task(
            user_id=user,
            project_id=project.id,
            title="Ship dashboard",
            status="Pending",
            importance="High",
            deadline=date.today() + timedelta(days=3),
            created_at=datetime.utcnow(),
        )
        db.session.add_all([blocked, due])
        db.session.commit()

        before = [(item.id, item.status, item.title) for item in Task.query.order_by(Task.id).all()]
        result = build_owned_home_intelligence(owner_id=user, today=date.today(), now=datetime.utcnow())
        after = [(item.id, item.status, item.title) for item in Task.query.order_by(Task.id).all()]

        payload = result.to_dict()
        assert before == after
        assert payload["verified_from_state"] is True
        assert payload["read_only"] is True
        assert payload["focus"]["priorities"][0]["category"] == "blocked_task"
        assert payload["focus"]["priorities"][0]["actions"]
        assert payload["deadlines"]["counts"]["matched"] >= 1
        assert payload["activity"]["total_items"] >= 1
        assert payload["briefing"]["signals"]


def test_i12_home_is_ownership_bounded(app, user):
    with app.app_context():
        own = _project(user, "Own")
        db.session.add(Task(user_id=user, project_id=own.id, title="Own task", status="Pending", importance="Medium"))

        other = User(name="Other", email="other-i12@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()
        hidden = _project(other.id, "Hidden")
        db.session.add(Task(user_id=other.id, project_id=hidden.id, title="Hidden blocker", status="Blocked", importance="Critical"))
        db.session.commit()

        payload = build_owned_home_intelligence(owner_id=user).to_dict()
        raw = str(payload)
        assert "Hidden blocker" not in raw
        assert "Hidden" not in raw
        assert all(item["project_id"] == own.id for item in payload["focus"]["priorities"])


def test_i12_home_api_exposes_product_state_without_internal_rag_details(client, app, user):
    with app.app_context():
        project = _project(user, "Visible")
        db.session.add(Task(user_id=user, project_id=project.id, title="Visible blocker", status="Blocked", importance="High"))
        db.session.commit()

    _login(client)
    response = client.get("/api/v1/intelligence/home")
    assert response.status_code == 200
    payload = response.get_json()["home"]
    assert payload["verified_from_state"] is True
    assert payload["read_only"] is True
    assert payload["focus"]["priorities"]
    raw = str(payload).lower()
    assert "tool_name" not in raw
    assert "chunk_id" not in raw
    assert "embedding" not in raw
    assert "system_prompt" not in raw

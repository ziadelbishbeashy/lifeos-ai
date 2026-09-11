from __future__ import annotations

from datetime import date, timedelta

from database import db
from models import Project, Task, User
from services.today_intelligence_service import build_owned_today_intelligence


def _project(user_id: int, title: str) -> Project:
    project = Project(
        user_id=user_id,
        title=title,
        status="In Progress",
        priority="Medium",
        progress=10,
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


def test_today_intelligence_ranks_trusted_attention_and_is_read_only(app, user):
    with app.app_context():
        project = _project(user, "LifeOS")
        blocked = Task(
            user_id=user,
            project_id=project.id,
            title="Fix production blocker",
            status="Blocked",
            importance="High",
        )
        due_later = Task(
            user_id=user,
            project_id=project.id,
            title="Polish dashboard",
            status="Pending",
            importance="Medium",
            deadline=date.today() + timedelta(days=3),
        )
        db.session.add_all([blocked, due_later])
        db.session.commit()

        before = [(item.id, item.status) for item in Task.query.order_by(Task.id).all()]
        result = build_owned_today_intelligence(owner_id=user)
        after = [(item.id, item.status) for item in Task.query.order_by(Task.id).all()]

        assert result.priorities
        assert result.priorities[0].category == "blocked_task"
        assert result.priorities[0].project_id == project.id
        assert result.attention_level == "high"
        assert before == after
        payload = result.to_dict()
        assert payload["verified_from_state"] is True
        assert payload["read_only"] is True


def test_today_intelligence_never_includes_other_users_projects(app, user):
    with app.app_context():
        own = _project(user, "Own Project")
        other = User(name="Other", email="other-today@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()
        hidden = _project(other.id, "Hidden Project")
        db.session.add(
            Task(
                user_id=other.id,
                project_id=hidden.id,
                title="Hidden blocker",
                status="Blocked",
                importance="Critical",
            )
        )
        db.session.commit()

        result = build_owned_today_intelligence(owner_id=user)
        assert result.total_owned_projects == 1
        assert all(item.project_id == own.id for item in result.priorities)
        assert "Hidden" not in result.summary


def test_today_intelligence_api_exposes_product_level_payload(client, app, user):
    with app.app_context():
        project = _project(user, "Visible Today Project")
        db.session.add(
            Task(
                user_id=user,
                project_id=project.id,
                title="Due today",
                status="Pending",
                importance="High",
                deadline=date.today(),
            )
        )
        db.session.commit()

    _login(client)
    response = client.get("/api/v1/intelligence/today")
    assert response.status_code == 200
    payload = response.get_json()["today"]
    assert payload["verified_from_state"] is True
    assert payload["read_only"] is True
    assert payload["priorities"]
    assert payload["priorities"][0]["project_title"] == "Visible Today Project"
    raw = str(payload).lower()
    assert "tool_name" not in raw
    assert "chunk_id" not in raw
    assert "embedding" not in raw

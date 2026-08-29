from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from database import db
from models import LifeOSActivityEvent, Note, Project, Task, User
from services.intelligence_action_service import (
    IntelligenceActionNotFoundError,
    IntelligenceActionValidationError,
    confirm_owned_action_proposal,
    create_priority_action_proposal,
    require_owned_proposal,
)
from services.intelligence_ask_service import ask_lifeos
from services.lifeos_activity_service import add_activity_event, build_owned_recent_activity


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


def _priority(project: Project, *, category: str = "document_risk") -> dict:
    return {
        "project_id": project.id,
        "project_title": project.title,
        "category": category,
        "severity": "high",
        "title": "Review documented risk: Checkout failure",
        "reason": "The current project plan identifies checkout as a delivery risk.",
        "recommended_action": "Create a concrete mitigation task.",
        "evidence": [
            {
                "source_type": "project",
                "source_id": project.id,
                "label": "Project state",
                "field": "risk",
                "freshness": "current",
            }
        ],
    }


def test_i9_proposal_does_not_write_until_confirm_and_executes_once(app, user):
    with app.app_context():
        project = _project(user, "LifeOS")
        proposal = create_priority_action_proposal(
            owner_id=user,
            action_type="create_task",
            priority=_priority(project),
        )

        assert proposal.status == "pending"
        assert Task.query.filter_by(user_id=user, project_id=project.id).count() == 0

        confirmed = confirm_owned_action_proposal(proposal_id=proposal.id, owner_id=user)
        assert confirmed.status == "confirmed"
        task = Task.query.filter_by(user_id=user, project_id=project.id).one()
        assert "Checkout failure" in task.title
        assert confirmed.execution_resource_type == "task"
        assert confirmed.execution_resource_id == task.id

        # Double confirmation must never execute the same action twice.
        with pytest.raises(IntelligenceActionValidationError):
            confirm_owned_action_proposal(proposal_id=proposal.id, owner_id=user)
        assert Task.query.filter_by(user_id=user, project_id=project.id).count() == 1

        event_types = {
            event.event_type
            for event in LifeOSActivityEvent.query.filter_by(user_id=user).all()
        }
        assert "task.created" in event_types
        assert "intelligence.action_confirmed" in event_types


def test_i9_create_note_action_uses_existing_note_service(app, user):
    with app.app_context():
        project = _project(user, "LifeOS")
        proposal = create_priority_action_proposal(
            owner_id=user,
            action_type="create_note",
            priority=_priority(project),
        )
        confirm_owned_action_proposal(proposal_id=proposal.id, owner_id=user)

        note = Note.query.filter_by(user_id=user, project_id=project.id).one()
        assert note.title.startswith("LifeOS insight:")
        assert "Checkout failure" in note.content


def test_i9_action_proposals_are_owner_isolated(app, user):
    with app.app_context():
        project = _project(user, "LifeOS")
        proposal = create_priority_action_proposal(
            owner_id=user,
            action_type="create_task",
            priority=_priority(project),
        )
        other = User(name="Other", email="other-i9@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()

        with pytest.raises(IntelligenceActionNotFoundError):
            require_owned_proposal(proposal_id=proposal.id, owner_id=other.id)
        with pytest.raises(IntelligenceActionNotFoundError):
            confirm_owned_action_proposal(proposal_id=proposal.id, owner_id=other.id)
        assert Task.query.filter_by(user_id=user, project_id=project.id).count() == 0


def test_i10_recent_activity_is_owner_and_project_scoped(app, user):
    with app.app_context():
        lifeos = _project(user, "LifeOS")
        store = _project(user, "Store")
        add_activity_event(
            user_id=user,
            event_type="project.updated",
            object_type="project",
            object_id=lifeos.id,
            project_id=lifeos.id,
            title="LifeOS phase updated",
            changes={"current_phase": {"from": "planning", "to": "development"}},
        )
        add_activity_event(
            user_id=user,
            event_type="task.created",
            object_type="task",
            object_id=999,
            project_id=store.id,
            title="Store task created",
        )
        db.session.commit()

        scoped = build_owned_recent_activity(
            owner_id=user,
            query="What changed this week?",
            project_id=lifeos.id,
        )
        assert scoped.project_title == "LifeOS"
        assert any("LifeOS phase" in item.title for item in scoped.items)
        assert all(item.project_id in (lifeos.id, None) for item in scoped.items)
        assert not any("Store task" in item.title for item in scoped.items)


def test_i10_derives_recent_state_for_pre_i10_records(app, user):
    with app.app_context():
        project = Project(
            user_id=user,
            title="Legacy Recent Project",
            status="In Progress",
            priority="Medium",
            progress=0,
            created_at=datetime.utcnow() - timedelta(hours=2),
            updated_at=datetime.utcnow() - timedelta(hours=2),
        )
        db.session.add(project)
        db.session.commit()

        result = build_owned_recent_activity(owner_id=user, query="What changed today?")
        assert any(
            item.source == "derived_state" and item.event_type == "project.created" and item.object_id == project.id
            for item in result.items
        )


def test_i10_ask_lifeos_executes_recent_activity_and_preserves_clarification(app, user):
    with app.app_context():
        lifeos = _project(user, "LifeOS")
        store = _project(user, "Store")
        add_activity_event(
            user_id=user,
            event_type="project.updated",
            object_type="project",
            object_id=lifeos.id,
            project_id=lifeos.id,
            title="LifeOS updated",
        )
        add_activity_event(
            user_id=user,
            event_type="project.updated",
            object_type="project",
            object_id=store.id,
            project_id=store.id,
            title="Store updated",
        )
        db.session.commit()

        direct = ask_lifeos(query="What changed in LifeOS this week?", owner_id=user)
        payload = direct.to_dict()
        assert payload["route"]["intent"] == "recent_activity"
        assert payload["route"]["scope"]["label"] == "LifeOS"
        assert payload["activity"]["verified_from_state"] is True
        assert any("LifeOS updated" == item["title"] for item in payload["activity"]["items"])

        first = ask_lifeos(query="What changed in my project this week?", owner_id=user)
        assert first.status == "clarification_required"
        assert first.route.intent == "recent_activity"
        second = ask_lifeos(
            query="LifeOS",
            owner_id=user,
            clarification_context={"intent": "recent_activity"},
        )
        assert second.status == "completed"
        assert second.route.intent == "recent_activity"
        assert second.route.scope_label == "LifeOS"

        all_projects = ask_lifeos(query="What changed across all my projects this week?", owner_id=user)
        assert all_projects.route.intent == "recent_activity"
        assert all_projects.route.scope_type == "portfolio"
        assert any(item["title"] == "Store updated" for item in all_projects.activity["items"])


def _login(client):
    return client.post(
        "/login",
        data={"email": "student@example.com", "password": "StrongPass123!"},
        follow_redirects=False,
    )


def test_i9_api_requires_explicit_second_confirm(client, app, user):
    with app.app_context():
        project = _project(user, "LifeOS")
        priority = _priority(project)

    _login(client)
    proposed = client.post(
        "/api/v1/intelligence/action-proposals",
        json={"action_type": "create_task", "priority": priority},
    )
    assert proposed.status_code == 201
    proposal = proposed.get_json()["proposal"]
    assert proposal["status"] == "pending"

    with app.app_context():
        assert Task.query.filter_by(user_id=user).count() == 0

    confirmed = client.post(f"/api/v1/intelligence/action-proposals/{proposal['id']}/confirm", json={})
    assert confirmed.status_code == 200
    assert confirmed.get_json()["proposal"]["status"] == "confirmed"
    with app.app_context():
        assert Task.query.filter_by(user_id=user).count() == 1


def test_i10_activity_api_returns_only_authenticated_users_history(client, app, user):
    with app.app_context():
        project = _project(user, "LifeOS")
        add_activity_event(
            user_id=user,
            event_type="project.updated",
            object_type="project",
            object_id=project.id,
            project_id=project.id,
            title="Visible activity",
        )
        other = User(name="Other", email="other-i10@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.flush()
        add_activity_event(
            user_id=other.id,
            event_type="project.updated",
            object_type="project",
            object_id=777,
            title="Hidden activity",
        )
        db.session.commit()

    _login(client)
    response = client.get("/api/v1/intelligence/activity?q=What%20changed%20today%3F")
    assert response.status_code == 200
    raw = str(response.get_json())
    assert "Visible activity" in raw
    assert "Hidden activity" not in raw


def test_i9_ask_lifeos_exposes_only_reviewed_action_choices(app, user):
    with app.app_context():
        project = _project(user, "LifeOS")
        result = ask_lifeos(query="What should I focus on in LifeOS?", owner_id=user)
        priority = result.to_dict()["agent"]["priorities"][0]
        assert priority["category"] == "missing_next_action"
        action_types = {item["type"] for item in priority["actions"]}
        assert action_types == {"create_task", "create_note"}

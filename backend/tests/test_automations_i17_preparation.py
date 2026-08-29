from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from database import db
from models import LifeOSAutomation, LifeOSAutomationRun, Project, Task, User
from services.automation_engine_service import collect_owned_automation_candidates
from services.automation_service import (
    AutomationNotFoundError,
    AutomationValidationError,
    automation_registry,
    calculate_next_run_at,
    create_owned_automation,
    list_owned_automations,
    preview_owned_automation,
    update_owned_automation,
)


def _project(user_id: int, title: str = "LifeOS") -> Project:
    project = Project(user_id=user_id, title=title, status="In Progress", priority="Medium", progress=20)
    db.session.add(project)
    db.session.commit()
    return project


def _login(client):
    return client.post(
        "/login",
        data={"email": "student@example.com", "password": "StrongPass123!"},
        follow_redirects=False,
    )


def test_i17_registry_is_constrained_and_background_execution_is_available_but_safe():
    registry = automation_registry()
    assert registry["safety"]["arbitrary_code"] is False
    assert registry["safety"]["arbitrary_sql"] is False
    assert registry["safety"]["workspace_mutation"] is False
    assert registry["safety"]["background_execution_available"] is True
    assert registry["safety"]["single_worker_v1"] is True
    assert "task.overdue" in registry["event_types"]
    assert {item["type"] for item in registry["actions"]} >= {"today_briefing", "portfolio_review", "attention_notice"}


def test_i17_schedule_calculation_uses_explicit_timezone_and_never_guesses():
    next_run = calculate_next_run_at(
        trigger_type="schedule_daily",
        trigger_config={"hour": 8, "minute": 0},
        timezone_name="UTC",
        now=datetime(2026, 8, 30, 7, 30),
    )
    assert next_run == datetime(2026, 8, 30, 8, 0)

    weekly = calculate_next_run_at(
        trigger_type="schedule_weekly",
        trigger_config={"weekday": 0, "hour": 8, "minute": 0},
        timezone_name="UTC",
        now=datetime(2026, 8, 30, 20, 0),  # Sunday
    )
    assert weekly == datetime(2026, 8, 31, 8, 0)


def test_i17_rejects_unreviewed_trigger_and_action(app, user):
    with app.app_context():
        with pytest.raises(AutomationValidationError):
            create_owned_automation(
                owner_id=user,
                name="Unsafe shell",
                trigger_type="schedule_daily",
                trigger_config={"hour": 8, "minute": 0},
                action_type="run_shell",
                action_config={"command": "rm -rf /"},
                timezone_name="UTC",
            )
        with pytest.raises(AutomationValidationError):
            create_owned_automation(
                owner_id=user,
                name="Unsafe webhook",
                trigger_type="event",
                trigger_config={"event_type": "arbitrary.webhook"},
                action_type="attention_notice",
                action_config={},
                timezone_name="UTC",
            )


def test_i17_definitions_and_updates_are_owner_isolated(app, user):
    with app.app_context():
        automation = create_owned_automation(
            owner_id=user,
            name="Morning briefing",
            trigger_type="schedule_daily",
            trigger_config={"hour": 8, "minute": 0},
            action_type="today_briefing",
            action_config={},
            timezone_name="UTC",
        )
        other = User(name="Other", email="i17-other@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()

        assert len(list_owned_automations(owner_id=user)) == 1
        assert list_owned_automations(owner_id=other.id) == ()
        with pytest.raises(AutomationNotFoundError):
            update_owned_automation(owner_id=other.id, automation_id=automation.id, payload={"enabled": True})


def test_i17_preview_is_audited_but_does_not_mutate_workspace(app, user):
    with app.app_context():
        project = _project(user)
        task = Task(user_id=user, project_id=project.id, title="Keep me unchanged", status="Pending", importance="Medium", difficulty="Medium")
        db.session.add(task)
        db.session.commit()
        before = (Task.query.filter_by(user_id=user).count(), task.status, task.deadline)

        automation = create_owned_automation(
            owner_id=user,
            name="Today preview",
            trigger_type="schedule_daily",
            trigger_config={"hour": 8, "minute": 0},
            action_type="today_briefing",
            action_config={},
            timezone_name="UTC",
        )
        result = preview_owned_automation(owner_id=user, automation_id=automation.id)
        db.session.refresh(task)
        after = (Task.query.filter_by(user_id=user).count(), task.status, task.deadline)

        assert result.to_dict()["workspace_mutation"] is False
        assert before == after
        assert LifeOSAutomationRun.query.filter_by(user_id=user, automation_id=automation.id, dry_run=True).count() == 1


def test_i17_preparation_cycle_matches_i14_event_but_executes_nothing(app, user):
    with app.app_context():
        project = _project(user)
        db.session.add(Task(
            user_id=user,
            project_id=project.id,
            title="Overdue launch task",
            status="Pending",
            importance="High",
            difficulty="Medium",
            deadline=date.today() - timedelta(days=1),
        ))
        automation = create_owned_automation(
            owner_id=user,
            name="Overdue watch",
            enabled=True,
            trigger_type="event",
            trigger_config={"event_type": "task.overdue"},
            action_type="attention_notice",
            action_config={},
            timezone_name="UTC",
        )
        db.session.commit()

        cycle = collect_owned_automation_candidates(owner_id=user)
        matching = [item for item in cycle.candidates if item.automation_id == automation.id and item.event_type == "task.overdue"]
        assert len(matching) == 1
        payload = cycle.to_dict()
        assert payload["actions_executed"] == 0
        assert payload["workspace_mutation"] is False


def test_i17_api_exposes_registry_crud_and_preview(client, app, user):
    _login(client)
    registry = client.get("/api/v1/automations/registry")
    assert registry.status_code == 200
    assert registry.get_json()["registry"]["safety"]["background_execution_available"] is True
    assert registry.get_json()["runtime"]["execution_available"] is True

    created = client.post("/api/v1/automations", json={
        "name": "Daily briefing",
        "trigger_type": "schedule_daily",
        "trigger_config": {"hour": 8, "minute": 0},
        "action_type": "today_briefing",
        "action_config": {},
        "timezone": "UTC",
    })
    assert created.status_code == 201
    automation_id = created.get_json()["automation"]["id"]

    preview = client.post(f"/api/v1/automations/{automation_id}/preview", json={})
    assert preview.status_code == 200
    assert preview.get_json()["preview"]["workspace_mutation"] is False

    listed = client.get("/api/v1/automations")
    assert listed.status_code == 200
    assert listed.get_json()["count"] == 1

    removed = client.delete(f"/api/v1/automations/{automation_id}")
    assert removed.status_code == 200
    with app.app_context():
        assert LifeOSAutomation.query.filter_by(user_id=user).count() == 0

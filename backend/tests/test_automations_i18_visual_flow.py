from __future__ import annotations

import pytest

from database import db
from models import Project
from services.automation_service import (
    AutomationValidationError,
    automation_registry,
    automation_to_dict,
    create_owned_automation,
    update_owned_automation,
    validate_visual_graph,
)


def _project(user_id: int, title: str = "LifeOS") -> Project:
    item = Project(user_id=user_id, title=title, status="In Progress", priority="Medium", progress=20)
    db.session.add(item)
    db.session.commit()
    return item


def _login(client):
    return client.post(
        "/login",
        data={"email": "student@example.com", "password": "StrongPass123!"},
        follow_redirects=False,
    )


def _graph(x: float = 70, y: float = 120):
    return {
        "version": 1,
        "nodes": [
            {"id": "trigger", "kind": "trigger", "position": {"x": x, "y": y}},
            {"id": "intelligence", "kind": "intelligence", "position": {"x": 380, "y": 140}},
            {"id": "delivery", "kind": "delivery", "position": {"x": 700, "y": 160}},
        ],
        "edges": [
            {"id": "a", "source": "trigger", "target": "intelligence"},
            {"id": "b", "source": "intelligence", "target": "delivery"},
        ],
    }


def test_i18_registry_exposes_visual_builder_without_new_execution_runtime():
    registry = automation_registry()
    assert registry["visual_flow"]["version"] == 1
    assert registry["visual_flow"]["node_order"] == ["trigger", "intelligence", "delivery"]
    assert registry["visual_flow"]["connections_fixed"] is True
    assert registry["visual_flow"]["layout_persisted"] is True
    assert registry["visual_flow"]["execution_source"] == "I17_allowlisted_trigger_and_action"
    assert registry["safety"]["workspace_mutation"] is False


def test_i18_visual_layout_persists_but_execution_semantics_stay_in_i17_columns(app, user):
    with app.app_context():
        item = create_owned_automation(
            owner_id=user,
            name="Visual morning flow",
            trigger_type="schedule_daily",
            trigger_config={"hour": 8, "minute": 15},
            action_type="today_briefing",
            action_config={},
            timezone_name="UTC",
            visual_graph=_graph(112, 99),
        )
        payload = automation_to_dict(item)
        nodes = {node["id"]: node for node in payload["visual_graph"]["nodes"]}
        assert nodes["trigger"]["position"] == {"x": 112.0, "y": 99.0}
        assert nodes["trigger"]["semantic_type"] == "schedule_daily"
        assert nodes["intelligence"]["semantic_type"] == "today_briefing"
        assert nodes["delivery"]["semantic_type"] == "in_app_notification"
        assert payload["safety"]["workspace_mutation"] is False


def test_i18_rejects_arbitrary_nodes_or_rewired_edges():
    bad_node = _graph()
    bad_node["nodes"].append({"id": "shell", "kind": "shell", "position": {"x": 1, "y": 1}})
    with pytest.raises(AutomationValidationError):
        validate_visual_graph(bad_node, trigger_type="schedule_daily", action_type="today_briefing")

    rewired = _graph()
    rewired["edges"] = [
        {"id": "a", "source": "trigger", "target": "delivery"},
        {"id": "b", "source": "delivery", "target": "intelligence"},
    ]
    with pytest.raises(AutomationValidationError):
        validate_visual_graph(rewired, trigger_type="schedule_daily", action_type="today_briefing")


def test_i18_editing_visual_flow_cannot_bypass_project_ownership(app, user):
    with app.app_context():
        owned = _project(user, "Owned")
        item = create_owned_automation(
            owner_id=user,
            name="Owned project review",
            trigger_type="schedule_weekly",
            trigger_config={"weekday": 0, "hour": 9, "minute": 0},
            action_type="project_review",
            action_config={"project_id": owned.id},
            timezone_name="UTC",
            visual_graph=_graph(),
        )
        with pytest.raises(AutomationValidationError):
            update_owned_automation(
                owner_id=user,
                automation_id=item.id,
                payload={
                    "action_type": "project_review",
                    "action_config": {"project_id": owned.id + 99999},
                    "visual_graph": _graph(),
                },
            )


def test_i18_api_accepts_and_returns_visual_graph(client, app, user):
    _login(client)
    created = client.post("/api/v1/automations", json={
        "name": "Canvas flow",
        "trigger_type": "schedule_daily",
        "trigger_config": {"hour": 10, "minute": 5},
        "action_type": "today_briefing",
        "action_config": {},
        "timezone": "UTC",
        "visual_graph": _graph(140, 130),
    })
    assert created.status_code == 201
    body = created.get_json()["automation"]
    assert body["visual_graph"]["version"] == 1
    assert body["visual_graph"]["nodes"][0]["position"]["x"] == 140.0

    automation_id = body["id"]
    updated = client.patch(f"/api/v1/automations/{automation_id}", json={
        "visual_graph": _graph(222, 111),
    })
    assert updated.status_code == 200
    nodes = {node["id"]: node for node in updated.get_json()["automation"]["visual_graph"]["nodes"]}
    assert nodes["trigger"]["position"] == {"x": 222.0, "y": 111.0}

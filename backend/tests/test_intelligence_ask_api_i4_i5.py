from __future__ import annotations

import json

from database import db
from models import Project, Task


def _login(client):
    return client.post(
        "/login",
        data={"email": "student@example.com", "password": "StrongPass123!"},
        follow_redirects=False,
    )


def _provider_config():
    return {"provider": "gemini", "api_key": "test-key", "model": "test-model"}


def test_ask_lifeos_api_returns_verified_product_level_answer(client, app, user, monkeypatch):
    with app.app_context():
        project = Project(
            user_id=user,
            title="LifeOS",
            status="In Progress",
            priority="Medium",
            progress=5,
        )
        db.session.add(project)
        db.session.commit()
        db.session.add(Task(user_id=user, project_id=project.id, title="Build intelligence", status="Pending"))
        db.session.commit()

    reasoning = json.dumps(
        {
            "answer": "LifeOS is in progress with one open task and no overdue work.",
            "factual_claims": [
                {
                    "text": "LifeOS is In Progress.",
                    "facts": [{"key": "project.status", "value": "In Progress"}],
                },
                {
                    "text": "There is one task and none are overdue.",
                    "facts": [
                        {"key": "project.total_tasks", "value": 1},
                        {"key": "project.overdue_tasks", "value": 0},
                    ],
                },
            ],
            "inferences": [],
            "recommendations": [],
        }
    )
    monkeypatch.setattr("services.intelligence_reasoning_service.get_ai_configuration", _provider_config)
    monkeypatch.setattr("services.intelligence_claim_verifier_service.get_ai_configuration", _provider_config)
    monkeypatch.setattr("services.intelligence_reasoning_service.route_ai_text", lambda **kwargs: reasoning)
    monkeypatch.setattr(
        "services.intelligence_claim_verifier_service.route_ai_text",
        lambda **kwargs: json.dumps({"verified": True, "issues": []}),
    )

    _login(client)
    response = client.post(
        "/api/v1/intelligence/ask",
        json={"query": "How is my LifeOS project going?"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["response_mode"] == "ai_verified"
    assert payload["verification"]["status"] == "verified"
    assert payload["route"]["scope"]["label"] == "LifeOS"
    serialized = json.dumps(payload).lower()
    assert "tool_data" not in serialized
    assert "router_version" not in serialized
    assert "api_key" not in serialized
    assert "provider" not in serialized
    assert "model" not in serialized
    assert "issues" not in payload["verification"]

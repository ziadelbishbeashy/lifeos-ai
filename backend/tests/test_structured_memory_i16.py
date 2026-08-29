from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from database import db
from models import LifeOSMemory, Project, User
from services.intelligence_ask_service import ask_lifeos
from services.intelligence_context_service import collect_owned_project_context
from services.structured_memory_service import (
    StructuredMemoryNotFoundError,
    clear_owned_memories,
    delete_owned_memory,
    list_owned_memories,
    refresh_owned_structured_memory,
    save_owned_user_memory,
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


def test_i16_user_memory_is_explicit_inspectable_and_owner_isolated(app, user):
    with app.app_context():
        saved = save_owned_user_memory(
            owner_id=user,
            memory_type="preference",
            label="Review style",
            value="Keep project reviews concise and prioritize blockers.",
        )
        assert saved.user_confirmed is True
        assert saved.value["text"].startswith("Keep project reviews")

        other = User(name="Other", email="i16-other@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()

        assert len(list_owned_memories(owner_id=user).items) == 1
        assert list_owned_memories(owner_id=other.id).items == ()

        with pytest.raises(StructuredMemoryNotFoundError):
            delete_owned_memory(owner_id=other.id, memory_id=saved.id)
        delete_owned_memory(owner_id=user, memory_id=saved.id)
        assert LifeOSMemory.query.filter_by(user_id=user).count() == 0


def test_i16_current_focus_replaces_previous_value(app, user):
    with app.app_context():
        save_owned_user_memory(owner_id=user, memory_type="current_focus", label="Current focus", value="Finish I16")
        save_owned_user_memory(owner_id=user, memory_type="current_focus", label="Current focus", value="Verify I16")
        items = list_owned_memories(owner_id=user, memory_type="current_focus").items
        assert len(items) == 1
        assert items[0].value["text"] == "Verify I16"


def test_i16_refresh_remembers_recent_owned_projects_without_document_or_chat_content(app, user):
    with app.app_context():
        project = _project(user, "LifeOS")
        project.updated_at = datetime.utcnow()
        other = User(name="Other", email="i16-recent-other@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.flush()
        hidden = Project(user_id=other.id, title="Hidden project", status="In Progress", updated_at=datetime.utcnow())
        db.session.add(hidden)
        db.session.commit()

        result = refresh_owned_structured_memory(owner_id=user)
        recent = [item for item in result.items if item.memory_type == "recent_project"]
        assert any(item.scope_id == project.id for item in recent)
        assert all(item.scope_id != hidden.id for item in recent)
        raw = str(result.to_dict())
        assert "Hidden project" not in raw
        assert "stores_chat_transcripts': False" in raw
        assert "stores_raw_document_text': False" in raw


def test_i16_explicit_memory_is_added_to_verified_project_context(app, user):
    with app.app_context():
        project = _project(user)
        save_owned_user_memory(
            owner_id=user,
            memory_type="preference",
            label="Review style",
            value="Prioritize blockers before cosmetic work.",
            project_id=project.id,
        )
        context = collect_owned_project_context(project_id=project.id, owner_id=user)
        memory_facts = [fact for fact in context.facts if fact.key.startswith("memory.preference.")]
        assert len(memory_facts) == 1
        assert memory_facts[0].value == "Prioritize blockers before cosmetic work."
        assert memory_facts[0].evidence[0].source_type == "memory"


def test_i16_ask_lifeos_can_explain_memory_without_ai_guessing(app, user):
    with app.app_context():
        save_owned_user_memory(
            owner_id=user,
            memory_type="current_focus",
            label="Current focus",
            value="Finish core intelligence before automations.",
        )
        result = ask_lifeos(query="What do you remember about my workspace?", owner_id=user).to_dict()
        assert result["route"]["intent"] == "memory_query"
        assert result["response_mode"] == "deterministic_verified"
        assert result["memory"]["user_controlled"] is True
        assert "structured LifeOS memory" in result["answer"]
        assert "Finish core intelligence" in str(result["memory"])


def test_i16_api_save_delete_and_clear_are_authenticated_owner_only(client, app, user):
    _login(client)
    saved = client.post("/api/v1/intelligence/memory", json={
        "type": "preference",
        "label": "Answer style",
        "value": "Keep answers short.",
    })
    assert saved.status_code == 201
    memory_id = saved.get_json()["memory"]["id"]

    listed = client.get("/api/v1/intelligence/memory")
    assert listed.status_code == 200
    assert any(item["id"] == memory_id for item in listed.get_json()["memory"]["items"])

    deleted = client.delete(f"/api/v1/intelligence/memory/{memory_id}")
    assert deleted.status_code == 200
    assert deleted.get_json()["deleted"] is True

    cleared = client.post("/api/v1/intelligence/memory/clear", json={})
    assert cleared.status_code == 200
    assert cleared.get_json()["deleted"] >= 0


def test_i16_clear_really_forgets_rows(app, user):
    with app.app_context():
        save_owned_user_memory(owner_id=user, memory_type="preference", label="One", value="First")
        save_owned_user_memory(owner_id=user, memory_type="preference", label="Two", value="Second")
        assert clear_owned_memories(owner_id=user) == 2
        assert LifeOSMemory.query.filter_by(user_id=user).count() == 0

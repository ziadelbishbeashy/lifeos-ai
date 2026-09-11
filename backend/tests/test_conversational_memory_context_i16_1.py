from __future__ import annotations

from types import SimpleNamespace

from database import db
from models import Document, LifeOSMemory, Project, User
from services.ask_context_picker_service import (
    AskContextNotFoundError,
    list_owned_ask_context_options,
    validate_owned_ask_context,
)
from services.intelligence_ask_service import ask_lifeos
from services.structured_memory_service import list_owned_memories, save_owned_user_memory


def _project(user_id: int, title: str = "LifeOS") -> Project:
    row = Project(user_id=user_id, title=title, status="In Progress", priority="Medium", progress=10)
    db.session.add(row)
    db.session.commit()
    return row


def _document(user_id: int, project_id: int, filename: str = "Plan.pdf") -> Document:
    row = Document(
        user_id=user_id,
        project_id=project_id,
        filename=filename,
        file_path=f"tests/{filename}",
        extracted_text="Checkout must be disabled if order creation fails.",
        is_current_version=True,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _login(client):
    return client.post(
        "/login",
        data={"email": "student@example.com", "password": "StrongPass123!"},
        follow_redirects=False,
    )


def test_i16_1_context_picker_lists_only_owned_resources(app, user):
    with app.app_context():
        project = _project(user, "LifeOS")
        document = _document(user, project.id, "Owned.pdf")

        other = User(name="Other", email="i161-other@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()
        hidden_project = _project(other.id, "Hidden")
        hidden_document = _document(other.id, hidden_project.id, "Private.pdf")

        payload = list_owned_ask_context_options(owner_id=user)
        labels = str(payload)
        assert "LifeOS" in labels
        assert "Owned.pdf" in labels
        assert "Hidden" not in labels
        assert "Private.pdf" not in labels
        assert payload["selection_mode"] == "single"

        selected = validate_owned_ask_context(
            owner_id=user,
            raw_context={"type": "document", "id": document.id},
        )
        assert selected.label == "Owned.pdf"

        try:
            validate_owned_ask_context(
                owner_id=user,
                raw_context={"type": "document", "id": hidden_document.id},
            )
        except AskContextNotFoundError:
            pass
        else:
            raise AssertionError("Other users' context must never be selectable")


def test_i16_1_selected_project_removes_scope_guessing(app, user):
    with app.app_context():
        lifeos = _project(user, "LifeOS")
        _project(user, "Store")
        result = ask_lifeos(
            query="How is it going?",
            owner_id=user,
            selected_context={"type": "project", "id": lifeos.id},
        ).to_dict()
        assert result["route"]["scope"]["id"] == lifeos.id
        assert result["route"]["scope"]["label"] == "LifeOS"
        assert result["route"]["requires_clarification"] is False
        assert result["route"]["intent"] == "project_review"


def test_i16_1_selected_document_uses_existing_grounded_rag(monkeypatch, app, user):
    with app.app_context():
        project = _project(user)
        document = _document(user, project.id, "Deployment.pdf")

        fake_question = SimpleNamespace(
            id=77,
            answer="Checkout failure blocks new orders.",
            sources=[{"filename": "Deployment.pdf", "page": 3}],
        )
        fake_saved = SimpleNamespace(question=fake_question, reused_existing=False)
        monkeypatch.setattr(
            "services.intelligence_ask_service.ask_owned_document",
            lambda **kwargs: fake_saved,
        )

        result = ask_lifeos(
            query="What is the biggest checkout risk?",
            owner_id=user,
            selected_context={"type": "document", "id": document.id},
        ).to_dict()
        assert result["route"]["intent"] == "document_question"
        assert result["route"]["scope"]["label"] == "Deployment.pdf"
        assert result["response_mode"] == "grounded_rag_verified"
        assert result["grounded"]["source_count"] == 1
        assert result["grounded"]["verified_grounding"] is True


def test_i16_1_conversation_memory_is_proposed_not_silently_saved(app, user):
    with app.app_context():
        project = _project(user)
        result = ask_lifeos(
            query="I prefer short project reviews with important risks first.",
            owner_id=user,
            selected_context={"type": "project", "id": project.id},
        ).to_dict()
        assert result["route"]["intent"] == "memory_candidate"
        assert result["status"] == "memory_confirmation_required"
        assert result["memory_suggestion"]["type"] == "preference"
        assert result["memory_suggestion"]["project_id"] == project.id
        assert result["memory_suggestion"]["requires_confirmation"] is True
        assert list_owned_memories(owner_id=user).items == ()
        assert LifeOSMemory.query.filter_by(user_id=user).count() == 0


def test_i16_1_memory_propose_api_requires_separate_confirm_save(client, app, user):
    _login(client)
    proposed = client.post(
        "/api/v1/intelligence/memory/propose",
        json={"text": "I prefer concise answers with risks first."},
    )
    assert proposed.status_code == 200
    suggestion = proposed.get_json()["suggestion"]
    assert suggestion["type"] == "preference"

    with app.app_context():
        assert LifeOSMemory.query.filter_by(user_id=user).count() == 0

    saved = client.post(
        "/api/v1/intelligence/memory",
        json={
            "type": suggestion["type"],
            "label": suggestion["label"],
            "value": suggestion["value"],
            "project_id": suggestion["project_id"],
        },
    )
    assert saved.status_code == 201
    with app.app_context():
        assert LifeOSMemory.query.filter_by(user_id=user).count() == 1


def test_i16_1_memory_question_understands_natural_preference_wording(app, user):
    with app.app_context():
        save_owned_user_memory(
            owner_id=user,
            memory_type="preference",
            label="Project review style",
            value="Keep project reviews concise and put important risks first.",
        )
        result = ask_lifeos(query="How do I prefer my project reviews?", owner_id=user).to_dict()
        assert result["route"]["intent"] == "memory_query"
        assert result["response_mode"] == "deterministic_verified"
        assert "important risks first" in result["answer"]

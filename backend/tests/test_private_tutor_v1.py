from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from database import db
from models import PrivateTutorSession, User
from services.module_service import create_module
from services.private_tutor_service import (
    PrivateTutorNotFoundError,
    generate_owned_tutor_session,
    grade_owned_tutor_quiz,
    require_owned_tutor_session,
    serialize_tutor_session,
)


class FakeRetrieved:
    def __init__(self):
        self.text = "Merge sort splits the input, recursively sorts each half, and merges them in O(n log n) time."
        self.matched_terms = ("merge", "sort")

    def source(self):
        return {
            "document_id": 91,
            "filename": "sorting.pdf",
            "page": 4,
            "section": "Merge sort",
            "content_type": "text",
            "table_id": None,
        }


def _patch_tutor(monkeypatch, *, raw: dict):
    import services.private_tutor_service as tutor

    monkeypatch.setattr(tutor, "list_owned_module_scope_documents", lambda **kwargs: [SimpleNamespace(id=91)])
    monkeypatch.setattr(
        tutor,
        "retrieve_owned_document_set",
        lambda **kwargs: SimpleNamespace(query=kwargs["query"], chunks=[FakeRetrieved()]),
    )
    monkeypatch.setattr(tutor, "build_scope_context", lambda result: '[Source 1 | Document "sorting.pdf" | Page 4]\nMerge sort is O(n log n).')
    monkeypatch.setattr(tutor, "get_ai_configuration", lambda: {"provider": "test", "api_key": "secret", "model": "tutor-test"})
    monkeypatch.setattr(tutor, "route_ai_text", lambda **kwargs: json.dumps(raw))


def test_private_tutor_quiz_is_grounded_saved_and_graded_deterministically(app, user, monkeypatch):
    with app.app_context():
        module = create_module(user_id=user, title="Algorithms", subject="Computer Science")
        _patch_tutor(monkeypatch, raw={
            "title": "Merge sort check",
            "instructions": "Choose the best answer.",
            "questions": [
                {
                    "prompt": "What is the typical time complexity of merge sort?",
                    "options": ["O(n)", "O(n log n)", "O(n²)", "O(log n)"],
                    "correct_index": 1,
                    "explanation": "The selected material states that merge sort runs in O(n log n).",
                    "topic": "Merge sort complexity",
                    "source_ids": [1],
                },
                {
                    "prompt": "What core operation follows recursively sorting the halves?",
                    "options": ["Hashing", "Merging", "Sampling", "Pruning"],
                    "correct_index": 1,
                    "explanation": "The material describes splitting, recursively sorting, then merging.",
                    "topic": "Merge process",
                    "source_ids": [1],
                },
                {
                    "prompt": "Which design idea is reflected by splitting into halves?",
                    "options": ["Divide and conquer", "Greedy choice", "Backtracking", "Memoization"],
                    "correct_index": 0,
                    "explanation": "Splitting and recursively solving the halves is the divide-and-conquer structure described by the evidence.",
                    "topic": "Algorithm structure",
                    "source_ids": [1],
                },
            ],
            "study_tip": "Review the merge step if you miss a question.",
        })

        session = generate_owned_tutor_session(
            user_id=user,
            module_id=module.id,
            lecture_id=None,
            mode="quiz",
            topic="merge sort",
            request_text="Quiz me on merge sort",
            difficulty="intermediate",
            question_count=3,
        )
        assert session.id is not None
        assert session.sources[0]["filename"] == "sorting.pdf"
        public = serialize_tutor_session(session)
        assert "correct_index" not in public["content"]["questions"][0]
        assert "explanation" not in public["content"]["questions"][0]

        grade = grade_owned_tutor_quiz(
            session_id=session.id,
            user_id=user,
            answers={"q1": 1, "q2": 0, "q3": 0},
        )
        assert grade.correct == 2
        assert grade.total == 3
        assert grade.percentage == 67
        assert grade.weak_areas == ("Merge process",)

        saved = db.session.get(PrivateTutorSession, session.id)
        assert saved.status == "graded"
        assert saved.score_correct == 2
        assert saved.weak_areas == ["Merge process"]


def test_private_tutor_explanation_preserves_grounded_sources(app, user, monkeypatch):
    with app.app_context():
        module = create_module(user_id=user, title="Algorithms")
        _patch_tutor(monkeypatch, raw={
            "title": "Merge sort explained",
            "body_markdown": "## Idea\nMerge sort splits the input and merges sorted halves.",
            "key_points": [{"text": "The merge operation combines sorted halves.", "source_ids": [1]}],
            "check_questions": ["Why is merging necessary?"],
            "source_ids": [1],
        })
        session = generate_owned_tutor_session(
            user_id=user,
            module_id=module.id,
            lecture_id=None,
            mode="explain",
            topic="merge sort",
            request_text=None,
        )
        public = serialize_tutor_session(session)
        assert public["content"]["title"] == "Merge sort explained"
        assert public["content"]["key_points"][0]["source_ids"] == [1]
        assert public["sources"][0]["source_id"] == 1


def test_private_tutor_session_is_owner_scoped(app, user, monkeypatch):
    with app.app_context():
        other = User(name="Other learner", email="other-tutor@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()
        module = create_module(user_id=user, title="Private Algorithms")
        _patch_tutor(monkeypatch, raw={
            "title": "Revision cards",
            "cards": [{"front": "What does merge sort do?", "back": "It splits, recursively sorts, and merges.", "source_ids": [1]}],
        })
        session = generate_owned_tutor_session(
            user_id=user,
            module_id=module.id,
            lecture_id=None,
            mode="flashcards",
            topic="merge sort",
            request_text=None,
        )
        with pytest.raises(PrivateTutorNotFoundError):
            require_owned_tutor_session(session_id=session.id, user_id=other.id)


def test_private_tutor_api_lists_owned_modules(app, client, user):
    with app.app_context():
        create_module(user_id=user, title="Calculus")
    login = client.post("/api/v1/auth/login", json={"email": "student@example.com", "password": "StrongPass123!"})
    assert login.status_code == 200
    response = client.get("/api/v1/tutor")
    assert response.status_code == 200
    payload = response.get_json()
    assert [item["title"] for item in payload["modules"]] == ["Calculus"]
    assert payload["recent_sessions"] == []

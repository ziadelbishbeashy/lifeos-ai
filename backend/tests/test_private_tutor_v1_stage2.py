from __future__ import annotations

import json
from types import SimpleNamespace

from database import db
from models import PrivateTutorMastery, PrivateTutorSession
from services.module_service import create_module
from services.private_tutor_service import (
    build_revision_plan_recommendation,
    generate_owned_mistake_review,
    generate_owned_quiz_retry,
    generate_owned_tutor_follow_up,
    generate_owned_tutor_session,
    grade_owned_tutor_quiz,
    list_owned_tutor_conversation,
    list_owned_tutor_mastery,
)


class FakeRetrieved:
    def __init__(self):
        self.text = "Merge sort splits input, recursively sorts each half, and merges them in O(n log n) time."
        self.matched_terms = ("merge", "sort")

    def source(self):
        return {"document_id": 91, "filename": "sorting.pdf", "page": 4, "section": "Merge sort", "content_type": "text", "table_id": None}


def _quiz_raw(title="Merge sort quiz"):
    return {
        "title": title,
        "instructions": "Choose the best answer.",
        "questions": [
            {"prompt": "What is merge sort complexity?", "options": ["O(n)", "O(n log n)", "O(n²)"], "correct_index": 1, "explanation": "The source states O(n log n).", "topic": "Complexity", "source_ids": [1]},
            {"prompt": "What happens after sorting the halves?", "options": ["Merge", "Hash", "Prune"], "correct_index": 0, "explanation": "The sorted halves are merged.", "topic": "Merge step", "source_ids": [1]},
            {"prompt": "What pattern does splitting reflect?", "options": ["Greedy", "Divide and conquer", "Backtracking"], "correct_index": 1, "explanation": "The input is divided recursively.", "topic": "Structure", "source_ids": [1]},
        ],
        "study_tip": "Review missed concepts.",
    }


def _explain_raw(title="Targeted review"):
    return {
        "title": title,
        "body_markdown": "## Review\nMerge sort divides, sorts, and merges. Focus on the merge step and why it preserves order.",
        "key_points": [{"text": "Merging combines two sorted halves.", "source_ids": [1]}],
        "check_questions": ["Why must both halves be sorted before merging?"],
        "source_ids": [1],
    }


def _patch_tutor(monkeypatch):
    import services.private_tutor_service as tutor

    monkeypatch.setattr(tutor, "list_owned_module_scope_documents", lambda **kwargs: [SimpleNamespace(id=91)])
    monkeypatch.setattr(tutor, "retrieve_owned_document_set", lambda **kwargs: SimpleNamespace(query=kwargs["query"], chunks=[FakeRetrieved()]))
    monkeypatch.setattr(tutor, "build_scope_context", lambda result: '[Source 1 | Document "sorting.pdf" | Page 4]\nMerge sort is O(n log n).')
    monkeypatch.setattr(tutor, "get_ai_configuration", lambda: {"provider": "test", "api_key": "secret", "model": "tutor-test"})

    counter = {"quiz": 0}
    def respond(**kwargs):
        prompt = kwargs.get("prompt", "")
        if "MODE: quiz" in prompt:
            counter["quiz"] += 1
            return json.dumps(_quiz_raw(f"Merge sort quiz {counter['quiz']}"))
        return json.dumps(_explain_raw())
    monkeypatch.setattr(tutor, "route_ai_text", respond)


def test_stage2_quiz_updates_deterministic_mastery_and_revision_plan(app, user, monkeypatch):
    with app.app_context():
        module = create_module(user_id=user, title="Algorithms")
        _patch_tutor(monkeypatch)
        session = generate_owned_tutor_session(user_id=user, module_id=module.id, lecture_id=None, mode="quiz", topic="merge sort", request_text="Quiz me", question_count=3)
        grade = grade_owned_tutor_quiz(session_id=session.id, user_id=user, answers={"q1": 1, "q2": 1, "q3": 1})
        assert grade.percentage == 67
        rows = list_owned_tutor_mastery(user_id=user, module_id=module.id)
        by_topic = {row.topic_label: row for row in rows}
        assert by_topic["Complexity"].mastery_score == 100
        assert by_topic["Merge step"].mastery_score == 0
        assert by_topic["Structure"].mastery_score == 100
        plan = build_revision_plan_recommendation(db.session.get(PrivateTutorSession, session.id))
        assert plan["duration_minutes"] == 45
        assert "Merge step" in plan["prompt"]
        assert "re-quiz" in plan["prompt"]


def test_stage2_repeated_quiz_accumulates_mastery(app, user, monkeypatch):
    with app.app_context():
        module = create_module(user_id=user, title="Algorithms")
        _patch_tutor(monkeypatch)
        first = generate_owned_tutor_session(user_id=user, module_id=module.id, lecture_id=None, mode="quiz", topic="merge sort", request_text=None, question_count=3)
        grade_owned_tutor_quiz(session_id=first.id, user_id=user, answers={"q1": 0, "q2": 1, "q3": 0})
        second = generate_owned_quiz_retry(session_id=first.id, user_id=user)
        grade_owned_tutor_quiz(session_id=second.id, user_id=user, answers={"q1": 1, "q2": 0, "q3": 1})
        complexity = PrivateTutorMastery.query.filter_by(user_id=user, module_id=module.id, topic_key="complexity").one()
        assert complexity.quiz_attempts == 2
        assert complexity.question_count == 2
        assert complexity.correct_count == 1
        assert complexity.mastery_score == 50
        assert complexity.best_percentage == 100
        assert second.conversation_key == first.conversation_key
        assert second.parent_session_id == first.id


def test_stage2_follow_up_persists_same_conversation(app, user, monkeypatch):
    with app.app_context():
        module = create_module(user_id=user, title="Algorithms")
        _patch_tutor(monkeypatch)
        root = generate_owned_tutor_session(user_id=user, module_id=module.id, lecture_id=None, mode="explain", topic="merge sort", request_text="Explain merge sort")
        child = generate_owned_tutor_follow_up(session_id=root.id, user_id=user, request_text="Why does the merge step stay O(n)?")
        assert child.parent_session_id == root.id
        assert child.conversation_key == root.conversation_key
        rows = list_owned_tutor_conversation(conversation_key=root.conversation_key, user_id=user)
        assert [row.id for row in rows] == [root.id, child.id]
        assert child.request_text == "Why does the merge step stay O(n)?"


def test_stage2_mistake_review_is_grounded_child_session(app, user, monkeypatch):
    with app.app_context():
        module = create_module(user_id=user, title="Algorithms")
        _patch_tutor(monkeypatch)
        quiz = generate_owned_tutor_session(user_id=user, module_id=module.id, lecture_id=None, mode="quiz", topic="merge sort", request_text=None, question_count=3)
        grade_owned_tutor_quiz(session_id=quiz.id, user_id=user, answers={"q1": 1, "q2": 2, "q3": 1})
        review = generate_owned_mistake_review(session_id=quiz.id, user_id=user)
        assert review.mode == "explain"
        assert review.parent_session_id == quiz.id
        assert review.conversation_key == quiz.conversation_key
        assert review.sources[0]["filename"] == "sorting.pdf"
        assert "Merge step" in (review.topic or "")

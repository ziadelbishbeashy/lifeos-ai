from __future__ import annotations

import json
from types import SimpleNamespace

from database import db
from models import PrivateTutorMastery, PrivateTutorSession
from services.module_service import create_module
from services.private_tutor_personalization_service import (
    build_owned_course_profile,
    resolve_adaptive_difficulty,
    resolve_owned_study_intent,
)
from services.private_tutor_service import generate_owned_tutor_session


class FakeRetrieved:
    def __init__(self):
        self.text = "Integration by parts is derived from the product rule and is useful for products of functions."
        self.matched_terms = ("integration", "parts")

    def source(self):
        return {
            "document_id": 101,
            "filename": "calculus-notes.pdf",
            "page": 8,
            "section": "Integration by parts",
            "content_type": "text",
            "table_id": None,
        }


def _quiz_raw():
    return {
        "title": "Adaptive calculus check",
        "instructions": "Choose the best answer.",
        "questions": [
            {
                "prompt": "Which rule motivates integration by parts?",
                "options": ["Product rule", "Chain rule", "Quotient rule"],
                "correct_index": 0,
                "explanation": "The supplied material derives it from the product rule.",
                "topic": "Integration by parts",
                "source_ids": [1],
            },
            {
                "prompt": "When can integration by parts be useful?",
                "options": ["Products of functions", "Only constants", "Only limits"],
                "correct_index": 0,
                "explanation": "The source describes products of functions.",
                "topic": "Integration by parts",
                "source_ids": [1],
            },
            {
                "prompt": "What is the current study topic?",
                "options": ["Integration by parts", "Matrices", "Sorting"],
                "correct_index": 0,
                "explanation": "The selected evidence is about integration by parts.",
                "topic": "Integration by parts",
                "source_ids": [1],
            },
        ],
        "study_tip": "Review the product-rule derivation.",
    }


def test_stage3_natural_study_request_matches_owned_course(app, user):
    with app.app_context():
        calculus = create_module(user_id=user, title="Calculus", subject="Mathematics")
        create_module(user_id=user, title="Algorithms", subject="Computer Science")

        result = resolve_owned_study_intent(user_id=user, request_text="I want to study Calculus")

        assert result["status"] == "matched"
        assert result["selected_module_id"] == calculus.id
        assert result["confidence"] >= 0.7


def test_stage3_ambiguous_course_request_requires_user_choice(app, user):
    with app.app_context():
        create_module(user_id=user, title="Calculus I")
        create_module(user_id=user, title="Calculus II")

        result = resolve_owned_study_intent(user_id=user, request_text="study calculus")

        assert result["status"] == "ambiguous"
        assert result["selected_module_id"] is None
        assert len(result["candidates"]) >= 2


def test_stage3_unmatched_request_does_not_pretend_course_expertise(app, user):
    with app.app_context():
        create_module(user_id=user, title="Algorithms")

        result = resolve_owned_study_intent(user_id=user, request_text="I want to study organic chemistry")

        assert result["status"] == "no_match"
        assert result["selected_module_id"] is None


def test_stage3_course_profile_uses_material_and_mastery_history(app, user, monkeypatch):
    import services.private_tutor_personalization_service as personalization

    with app.app_context():
        module = create_module(user_id=user, title="Calculus")
        monkeypatch.setattr(
            personalization,
            "list_owned_module_scope_documents",
            lambda **kwargs: [SimpleNamespace(id=1), SimpleNamespace(id=2), SimpleNamespace(id=3)],
        )
        session = PrivateTutorSession(
            user_id=user,
            module_id=module.id,
            lecture_id=None,
            mode="quiz",
            difficulty="intermediate",
            conversation_key="calc-thread",
            topic="Integration by parts",
            content_json=json.dumps({"title": "Calculus baseline", "questions": []}),
            sources_json="[]",
            answers_json="{}",
            weak_areas_json=json.dumps(["Integration by parts"]),
            score_correct=1,
            score_total=3,
            status="graded",
            provider="test",
            model="test",
        )
        mastery = PrivateTutorMastery(
            user_id=user,
            module_id=module.id,
            topic_key="integration-by-parts",
            topic_label="Integration by parts",
            quiz_attempts=1,
            question_count=3,
            correct_count=1,
            mastery_score=33,
            best_percentage=33,
            last_percentage=33,
        )
        db.session.add_all([session, mastery])
        db.session.commit()

        profile = build_owned_course_profile(user_id=user, module_id=module.id)

        assert profile["expertise"] == "personalized_course_expert"
        assert profile["expert_ready"] is True
        assert profile["counts"]["documents"] == 3
        assert profile["counts"]["sessions"] == 1
        assert profile["overall_mastery"] == 33
        assert profile["weak_topics"][0]["topic"] == "Integration by parts"
        assert profile["recommendation"]["mode"] == "explain"
        assert profile["recommendation"]["difficulty"] == "adaptive"


def test_stage3_adaptive_difficulty_uses_topic_mastery(app, user):
    with app.app_context():
        module = create_module(user_id=user, title="Calculus")
        db.session.add(
            PrivateTutorMastery(
                user_id=user,
                module_id=module.id,
                topic_key="integration-by-parts",
                topic_label="Integration by parts",
                quiz_attempts=2,
                question_count=5,
                correct_count=2,
                mastery_score=40,
                best_percentage=60,
                last_percentage=40,
            )
        )
        db.session.commit()

        adaptive = resolve_adaptive_difficulty(
            user_id=user, module_id=module.id, topic="integration by parts"
        )

        assert adaptive["difficulty"] == "beginner"
        assert adaptive["score"] == 40
        assert adaptive["basis"] == "Integration by parts"


def test_stage3_broad_quiz_targets_weak_topics_and_adapts_level(app, user, monkeypatch):
    import services.private_tutor_personalization_service as personalization
    import services.private_tutor_service as tutor

    with app.app_context():
        module = create_module(user_id=user, title="Calculus")
        db.session.add(
            PrivateTutorMastery(
                user_id=user,
                module_id=module.id,
                topic_key="integration-by-parts",
                topic_label="Integration by parts",
                quiz_attempts=1,
                question_count=4,
                correct_count=1,
                mastery_score=25,
                best_percentage=25,
                last_percentage=25,
            )
        )
        db.session.commit()

        docs = [SimpleNamespace(id=101)]
        monkeypatch.setattr(personalization, "list_owned_module_scope_documents", lambda **kwargs: docs)
        monkeypatch.setattr(tutor, "list_owned_module_scope_documents", lambda **kwargs: docs)
        observed = {}

        def retrieve(**kwargs):
            observed["query"] = kwargs["query"]
            return SimpleNamespace(query=kwargs["query"], chunks=[FakeRetrieved()])

        monkeypatch.setattr(tutor, "retrieve_owned_document_set", retrieve)
        monkeypatch.setattr(tutor, "build_scope_context", lambda result: '[Source 1 | Document "calculus-notes.pdf" | Page 8]\nIntegration by parts comes from the product rule.')
        monkeypatch.setattr(tutor, "get_ai_configuration", lambda: {"provider": "test", "api_key": "secret", "model": "tutor-test"})

        def respond(**kwargs):
            observed["prompt"] = kwargs["prompt"]
            return json.dumps(_quiz_raw())

        monkeypatch.setattr(tutor, "route_ai_text", respond)

        session = generate_owned_tutor_session(
            user_id=user,
            module_id=module.id,
            lecture_id=None,
            mode="quiz",
            topic=None,
            request_text="I want to study Calculus",
            difficulty="adaptive",
            question_count=3,
        )

        assert observed["query"] == "Integration by parts"
        assert "PERSONALIZED LEARNING CONTEXT" in observed["prompt"]
        assert '"weak_topics": ["Integration by parts"]' in observed["prompt"]
        assert "DIFFICULTY: beginner" in observed["prompt"]
        assert session.difficulty == "beginner"

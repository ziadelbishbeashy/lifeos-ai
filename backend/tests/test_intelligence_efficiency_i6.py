from __future__ import annotations

import json

from database import db
from models import Project, Task
from services.intelligence_ask_service import ask_lifeos
from services.intelligence_claim_verifier_service import IntelligenceVerificationResult
from services.intelligence_context_service import collect_owned_project_context
from services.intelligence_reasoning_service import (
    BoundFact,
    IntelligenceReasoningResult,
    ReasoningClaim,
    reason_about_project_review,
)
from services.project_review_intelligence_service import review_project_context


def _project(user_id: int) -> Project:
    project = Project(
        user_id=user_id,
        title="LifeOS",
        status="In Progress",
        priority="Medium",
        progress=5,
        current_phase="planning and development",
    )
    db.session.add(project)
    db.session.commit()
    db.session.add(
        Task(
            user_id=user_id,
            project_id=project.id,
            title="Build intelligence",
            status="Pending",
        )
    )
    db.session.commit()
    return project


def _provider_config():
    return {"provider": "gemini", "api_key": "test-key", "model": "test-model"}


def _reasoning() -> IntelligenceReasoningResult:
    return IntelligenceReasoningResult(
        answer="LifeOS is in progress with one open task.",
        factual_claims=(
            ReasoningClaim(
                text="LifeOS is In Progress.",
                facts=(BoundFact("project.status", "In Progress"),),
            ),
            ReasoningClaim(
                text="There is one task.",
                facts=(BoundFact("project.total_tasks", 1),),
            ),
        ),
        inferences=(),
        recommendations=(),
        provider="fake",
        model="fake",
    )


def test_i6_review_can_be_built_from_existing_context_without_second_tool_run(app, user, monkeypatch):
    with app.app_context():
        project = _project(user)
        context = collect_owned_project_context(project_id=project.id, owner_id=user)

        # If the context-backed review accidentally tries to execute the project
        # plan again, this sentinel makes the regression obvious.
        monkeypatch.setattr(
            "services.project_review_intelligence_service.execute_intelligence_plan",
            lambda **kwargs: (_ for _ in ()).throw(AssertionError("duplicate tool execution")),
        )

        review = review_project_context(context=context)
        assert review.project["id"] == project.id
        assert any(item["key"] == "project.total_tasks" for item in review.facts)


def test_i6_reasoning_prompt_uses_compact_fact_projection(app, user, monkeypatch):
    with app.app_context():
        project = _project(user)
        context = collect_owned_project_context(project_id=project.id, owner_id=user)
        review = review_project_context(context=context)
        captured = {}

        monkeypatch.setattr(
            "services.intelligence_reasoning_service.get_ai_configuration",
            _provider_config,
        )

        def fake_provider(**kwargs):
            captured["prompt"] = kwargs["prompt"]
            return json.dumps(
                {
                    "answer": "LifeOS is in progress with one task.",
                    "factual_claims": [
                        {
                            "text": "LifeOS is In Progress.",
                            "facts": [{"key": "project.status", "value": "In Progress"}],
                        },
                        {
                            "text": "There is one task.",
                            "facts": [{"key": "project.total_tasks", "value": 1}],
                        },
                    ],
                    "inferences": [],
                    "recommendations": [],
                }
            )

        monkeypatch.setattr(
            "services.intelligence_reasoning_service.route_ai_text",
            fake_provider,
        )

        result = reason_about_project_review(
            query="How is my LifeOS project going?",
            context=context,
            review=review,
        )

        assert result.answer
        assert '"key": "project.status"' in captured["prompt"]
        assert '"fact_type": "verified"' in captured["prompt"]
        assert '"evidence":' not in captured["prompt"]
        assert '"recent_activity":' not in captured["prompt"]
        assert '"tool_data":' not in captured["prompt"]


def test_i6_ask_reuses_one_context_snapshot(app, user, monkeypatch):
    with app.app_context():
        _project(user)
        calls = {"context": 0}
        original_collect = collect_owned_project_context

        def counted_collect(**kwargs):
            calls["context"] += 1
            return original_collect(**kwargs)

        monkeypatch.setattr(
            "services.intelligence_ask_service.collect_owned_project_context",
            counted_collect,
        )
        monkeypatch.setattr(
            "services.intelligence_ask_service.reason_about_project_review",
            lambda **kwargs: _reasoning(),
        )
        monkeypatch.setattr(
            "services.intelligence_ask_service.verify_project_reasoning",
            lambda **kwargs: IntelligenceVerificationResult(
                verified=True,
                deterministic_checks_passed=True,
                prose_check_performed=True,
                issues=(),
                checked_factual_claims=2,
                checked_inferences=0,
                checked_recommendations=0,
            ),
        )

        result = ask_lifeos(query="How is my LifeOS project going?", owner_id=user)
        assert result.response_mode == "ai_verified"
        assert calls["context"] == 1

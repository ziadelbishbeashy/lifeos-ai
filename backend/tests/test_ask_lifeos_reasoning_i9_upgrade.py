from __future__ import annotations

import json

import pytest

from database import db
from models import LifeOSActionProposal, Project, Task, User
from services.intelligence_action_service import (
    IntelligenceActionValidationError,
    confirm_owned_action_proposal,
    create_priority_action_proposal,
    issue_priority_action_authorization,
)
from services.intelligence_ask_service import ask_lifeos
from services.intelligence_claim_verifier_service import deterministic_verify_reasoning
from services.intelligence_context_service import collect_owned_project_context
from services.intelligence_intent_router_service import route_intelligence_request
from services.intelligence_reasoning_service import (
    IntelligenceReasoningResult,
    ReasoningClaim,
    _build_reasoning_prompt,
    _normalise_reasoning_response,
)
from services.project_review_intelligence_service import review_project_context


def _project(user_id: int, title: str = "LifeOS") -> Project:
    project = Project(
        user_id=user_id,
        title=title,
        status="In Progress",
        priority="High",
        progress=55,
        current_phase="Development",
    )
    db.session.add(project)
    db.session.commit()
    return project


def _provider_config():
    return {"provider": "gemini", "api_key": "test-key", "model": "test-model"}


def _priority(project: Project) -> dict:
    return {
        "project_id": project.id,
        "project_title": project.title,
        "category": "document_risk",
        "severity": "high",
        "title": "Reduce release scope",
        "reason": "The project has launch-critical work competing with optional work.",
        "recommended_action": "Define the minimum release scope first.",
        "evidence": [
            {
                "source_type": "project",
                "source_id": project.id,
                "label": "Project state",
                "field": "priority",
                "freshness": "current",
            }
        ],
    }


def test_project_advice_routes_to_reasoner_but_factual_lookup_stays_deterministic(app, user):
    with app.app_context():
        _project(user)
        advice = route_intelligence_request(
            query="How can I simplify the LifeOS architecture and finish faster?",
            owner_id=user,
        )
        fact = route_intelligence_request(
            query="What is my LifeOS project progress?",
            owner_id=user,
        )
        assert advice.intent == "project_advice"
        assert advice.scope_type == "project"
        assert fact.intent == "project_question"


def test_advice_recommendation_can_use_domain_knowledge_without_faking_workspace_fact(app, user, monkeypatch):
    with app.app_context():
        project = _project(user)
        db.session.add(Task(user_id=user, project_id=project.id, title="Deploy", status="Pending"))
        db.session.commit()

        captured = {}
        advisory_json = json.dumps(
            {
                "answer": (
                    "Treat the saved project state as context, not as the solution. "
                    "I would freeze optional scope, define a minimum release path, and finish that path before adding more features."
                ),
                "factual_claims": [],
                "inferences": [],
                "recommendations": [
                    {
                        "text": "Freeze optional scope and define a minimum release path.",
                        "supporting_fact_keys": [],
                        "supporting_signal_titles": [],
                    }
                ],
            }
        )

        monkeypatch.setattr("services.intelligence_reasoning_service.get_ai_configuration", _provider_config)
        monkeypatch.setattr("services.intelligence_claim_verifier_service.get_ai_configuration", _provider_config)

        def fake_reasoner(**kwargs):
            captured["reasoner_prompt"] = kwargs["prompt"]
            return advisory_json

        def fake_verifier(**kwargs):
            captured["verifier_prompt"] = kwargs["prompt"]
            return json.dumps({"verified": True, "issues": []})

        monkeypatch.setattr("services.intelligence_reasoning_service.route_ai_text", fake_reasoner)
        monkeypatch.setattr("services.intelligence_claim_verifier_service.route_ai_text", fake_verifier)

        result = ask_lifeos(
            query="How can I simplify the LifeOS architecture and finish faster?",
            owner_id=user,
            selected_context={"type": "project", "id": project.id},
        )
        assert result.route.intent == "project_advice"
        assert result.response_mode == "ai_verified"
        assert "minimum release path" in (result.answer or "").lower()
        assert "do not merely summarize" in captured["reasoner_prompt"].lower()
        assert "may use outside knowledge" in captured["verifier_prompt"].lower()


def test_deterministic_verifier_allows_unsupported_recommendation_but_still_checks_named_support(app, user):
    with app.app_context():
        project = _project(user)
        context = collect_owned_project_context(project_id=project.id, owner_id=user)
        review = review_project_context(context=context)

        general_advice = IntelligenceReasoningResult(
            answer="Use a smaller release scope.",
            factual_claims=(),
            inferences=(),
            recommendations=(ReasoningClaim(text="Use a smaller release scope."),),
            provider="fake",
            model="fake",
        )
        ok, issues = deterministic_verify_reasoning(reasoning=general_advice, context=context, review=review)
        assert ok is True
        assert issues == ()

        bad_reference = IntelligenceReasoningResult(
            answer="Use a smaller release scope.",
            factual_claims=(),
            inferences=(),
            recommendations=(
                ReasoningClaim(
                    text="Use a smaller release scope.",
                    supporting_fact_keys=("project.fact_that_does_not_exist",),
                ),
            ),
            provider="fake",
            model="fake",
        )
        ok, issues = deterministic_verify_reasoning(reasoning=bad_reference, context=context, review=review)
        assert ok is False
        assert any("unknown fact key" in issue for issue in issues)


def test_i9_signed_priority_blocks_client_tampering_before_proposal_creation(app, user):
    with app.app_context():
        project = _project(user)
        priority = _priority(project)
        priority["i9_authorization"] = issue_priority_action_authorization(priority=priority, owner_id=user)

        proposal = create_priority_action_proposal(
            owner_id=user,
            action_type="create_task",
            priority=priority,
            require_signed_priority=True,
        )
        assert proposal.status == "pending"
        assert Task.query.filter_by(user_id=user, project_id=project.id).count() == 0

        tampered = dict(priority)
        tampered["title"] = "Client changed this recommendation"
        with pytest.raises(IntelligenceActionValidationError):
            create_priority_action_proposal(
                owner_id=user,
                action_type="create_task",
                priority=tampered,
                require_signed_priority=True,
            )


def test_i9_signed_priority_is_owner_bound_and_unsigned_priority_is_rejected(app, user):
    with app.app_context():
        project = _project(user)
        priority = _priority(project)
        token = issue_priority_action_authorization(priority=priority, owner_id=user)

        unsigned = dict(priority)
        with pytest.raises(IntelligenceActionValidationError):
            create_priority_action_proposal(
                owner_id=user,
                action_type="create_task",
                priority=unsigned,
                require_signed_priority=True,
            )

        other = User(name="Other", email="reasoning-i9-other@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()
        priority["i9_authorization"] = token
        with pytest.raises(IntelligenceActionValidationError):
            create_priority_action_proposal(
                owner_id=other.id,
                action_type="create_task",
                priority=priority,
                require_signed_priority=True,
            )


def test_i9_confirm_rejects_proposal_that_does_not_require_confirmation(app, user):
    with app.app_context():
        project = _project(user)
        proposal = LifeOSActionProposal(
            user_id=user,
            action_type="create_task",
            status="pending",
            title="Unsafe malformed proposal",
            reason="test",
            target_type="project",
            target_id=project.id,
            project_id=project.id,
            payload_json=json.dumps({"project_id": project.id, "title": "Should not execute"}),
            evidence_json="[]",
            risk_level="medium",
            requires_confirmation=False,
        )
        db.session.add(proposal)
        db.session.commit()

        with pytest.raises(IntelligenceActionValidationError):
            confirm_owned_action_proposal(proposal_id=proposal.id, owner_id=user)
        assert Task.query.filter_by(user_id=user, project_id=project.id).count() == 0


def test_i9_public_proposal_api_rejects_unsigned_client_priority(client, app, user):
    with app.app_context():
        project = _project(user)
        priority = _priority(project)

    client.post(
        "/login",
        data={"email": "student@example.com", "password": "StrongPass123!"},
        follow_redirects=False,
    )
    response = client.post(
        "/api/v1/intelligence/action-proposals",
        json={"action_type": "create_task", "priority": priority},
    )
    assert response.status_code == 400
    with app.app_context():
        assert LifeOSActionProposal.query.filter_by(user_id=user).count() == 0
        assert Task.query.filter_by(user_id=user).count() == 0


def test_simple_help_request_stays_advisory_while_release_goal_remains_agentic():
    from services.intelligence_ask_service import _looks_like_goal_request

    assert _looks_like_goal_request("Help me simplify this architecture") is False
    assert _looks_like_goal_request("Help me get this project ready for deployment") is True


def test_advisory_prompt_treats_context_as_evidence_and_adds_relevant_reasoning_lenses(app, user):
    with app.app_context():
        project = _project(user)
        context = collect_owned_project_context(project_id=project.id, owner_id=user)
        review = review_project_context(context=context)

        prompt = _build_reasoning_prompt(
            query="How can I simplify the backend architecture and finish faster?",
            context=context,
            review=review,
            mode="advisory",
        ).lower()

        assert "context is evidence, not the answer" in prompt
        assert "do not confuse \"grounded\" with \"restricted\"" in prompt
        assert "technical / architecture focus" in prompt
        assert "prioritization focus" in prompt
        assert "response quality gate" in prompt
        assert "cannot override ownership, i9 confirmation" in prompt


def test_reasoning_answer_preserves_short_paragraphs_and_bullets():
    raw = json.dumps(
        {
            "answer": "Main recommendation.\n\n- First step\n- Second step",
            "factual_claims": [],
            "inferences": [],
            "recommendations": [
                {
                    "text": "Use the two-step plan.",
                    "supporting_fact_keys": [],
                    "supporting_signal_titles": [],
                }
            ],
        }
    )
    result = _normalise_reasoning_response(raw, provider="fake", model="fake")
    assert "\n\n- First step\n- Second step" in result.answer


def test_i9_reuses_identical_pending_proposal_instead_of_accepting_replay(app, user):
    with app.app_context():
        project = _project(user)
        priority = _priority(project)
        priority["i9_authorization"] = issue_priority_action_authorization(priority=priority, owner_id=user)

        first = create_priority_action_proposal(
            owner_id=user,
            action_type="create_task",
            priority=priority,
            require_signed_priority=True,
        )
        second = create_priority_action_proposal(
            owner_id=user,
            action_type="create_task",
            priority=priority,
            require_signed_priority=True,
        )

        assert first.id == second.id
        assert LifeOSActionProposal.query.filter_by(
            user_id=user,
            project_id=project.id,
            status="pending",
        ).count() == 1


def test_deployment_question_routes_as_project_advice_and_gets_deployment_focus(app, user):
    from services.intelligence_intent_router_service import route_intelligence_request
    from services.intelligence_reasoning_service import _build_reasoning_prompt
    from services.intelligence_context_service import collect_owned_project_context
    from services.project_review_intelligence_service import review_project_context

    with app.app_context():
        project = _project(user)
        route = route_intelligence_request(
            query="What should I do to deploy this project?",
            owner_id=user,
            forced_project_id=project.id,
        )
        assert route.intent == "project_advice"

        context = collect_owned_project_context(project_id=project.id, owner_id=user)
        review = review_project_context(context=context)
        prompt = _build_reasoning_prompt(
            query="What should I do to deploy this project?",
            context=context,
            review=review,
            mode="advisory",
        ).lower()
        assert "deployment / release focus" in prompt
        assert "do not turn deployment planning into a project-status recap" in prompt
        assert "smallest practical next action" in prompt


def test_deployment_verifier_failure_returns_relevant_trusted_fallback(app, user, monkeypatch):
    from services.intelligence_ask_service import ask_lifeos

    with app.app_context():
        project = _project(user)
        db.session.add(Task(user_id=user, project_id=project.id, title="Production smoke test", status="Pending"))
        db.session.commit()

        advisory_json = json.dumps(
            {
                "answer": "Use a staged release path.",
                "factual_claims": [],
                "inferences": [],
                "recommendations": [
                    {
                        "text": "Use a staged release path.",
                        "supporting_fact_keys": [],
                        "supporting_signal_titles": [],
                    }
                ],
            }
        )
        monkeypatch.setattr("services.intelligence_reasoning_service.get_ai_configuration", _provider_config)
        monkeypatch.setattr("services.intelligence_claim_verifier_service.get_ai_configuration", _provider_config)
        monkeypatch.setattr(
            "services.intelligence_reasoning_service.route_ai_text",
            lambda **_kwargs: advisory_json,
        )
        monkeypatch.setattr(
            "services.intelligence_claim_verifier_service.route_ai_text",
            lambda **_kwargs: json.dumps({"verified": False, "issues": ["unsupported workspace claim"]}),
        )

        result = ask_lifeos(
            query="What should I do to deploy this project?",
            owner_id=user,
            selected_context={"type": "project", "id": project.id},
        )
        assert result.response_mode == "deterministic_fallback"
        answer = (result.answer or "").lower()
        assert "minimum release scope" in answer
        assert "staging smoke test" in answer
        assert "rollback plan" in answer
        assert "saved project progress" not in answer


def test_short_deployment_advice_does_not_force_i19_goal_plan():
    from services.intelligence_ask_service import _looks_like_goal_request

    assert _looks_like_goal_request("What should I do to deploy this project?") is False
    assert _looks_like_goal_request("Help me get this project ready for deployment") is True

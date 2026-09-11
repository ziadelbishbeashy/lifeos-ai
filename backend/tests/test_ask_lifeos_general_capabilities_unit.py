from __future__ import annotations

import pytest

from services.intelligence_capability_router_service import deterministic_request_profile
from services.safe_calculator_service import SafeCalculatorError, calculate_expression
from services.web_research_service import WebResearchPrivacyError, sanitize_public_web_query


def test_general_router_detects_public_web_without_domain_specific_intent():
    profile = deterministic_request_profile(
        query="Search the web for the latest official Flask security documentation",
        route_intent="general_conversation",
        selected_context_type=None,
    )
    assert profile.task_type == "research"
    assert profile.needs_web is True
    assert profile.action_mode == "read_only"


def test_general_router_detects_math_and_code_capabilities():
    math_profile = deterministic_request_profile(
        query="Calculate 2000 * 20 * 0.01",
        route_intent="general_conversation",
        selected_context_type=None,
    )
    assert math_profile.task_type == "calculate"
    assert math_profile.needs_calculator is True
    assert math_profile.calculator_expression == "2000 * 20 * 0.01"

    code_profile = deterministic_request_profile(
        query="Write Python code for a binary search function",
        route_intent="general_conversation",
        selected_context_type=None,
    )
    assert code_profile.needs_code is True
    assert code_profile.action_mode == "read_only"


def test_guidance_speech_acts_are_not_swallowed_by_generic_should_i_decision_rule():
    deploy = deterministic_request_profile(
        query="What should I do to deploy this project?",
        route_intent="project_advice",
        selected_context_type="project",
    )
    prioritize = deterministic_request_profile(
        query="What should I do next?",
        route_intent="project_advice",
        selected_context_type="project",
    )
    plan = deterministic_request_profile(
        query="How should I prepare for the release?",
        route_intent="project_advice",
        selected_context_type="project",
    )
    decision = deterministic_request_profile(
        query="Should I deploy now?",
        route_intent="project_advice",
        selected_context_type="project",
    )

    assert deploy.task_type == "advise"
    assert prioritize.task_type == "prioritize"
    assert plan.task_type == "plan"
    assert decision.task_type == "decide"


def test_selected_project_is_scope_not_reasoning_limit():
    profile = deterministic_request_profile(
        query="How can I simplify this and finish faster?",
        route_intent="project_advice",
        selected_context_type="project",
    )
    assert profile.needs_workspace is True
    assert profile.knowledge_scope == "workspace_plus_general"
    assert profile.action_mode == "recommendation"


def test_workspace_mutation_request_is_separate_from_advice():
    profile = deterministic_request_profile(
        query="Create a task for the fix you recommend",
        route_intent="project_advice",
        selected_context_type="project",
    )
    assert profile.task_type == "execute"
    assert profile.action_mode == "mutation_requested"
    assert profile.complexity == "multi_step"


def test_safe_calculator_computes_exact_result_without_eval():
    result = calculate_expression("2000 * 20 * 0.01")
    assert result.result == 400
    assert result.formatted_result == "400"
    assert result.to_dict()["code_execution"] is False


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('whoami')",
        "open('secret.txt')",
        "(1).__class__",
        "[x for x in range(5)]",
        "10 ** 100",
    ],
)
def test_safe_calculator_rejects_code_and_unbounded_expressions(expression: str):
    with pytest.raises(SafeCalculatorError):
        calculate_expression(expression)


def test_public_web_query_does_not_auto_leak_selected_context_label():
    query = sanitize_public_web_query(
        proposed_query="latest deployment guidance Secret Internal Project",
        original_query="What is the latest deployment guidance?",
        selected_context_label="Secret Internal Project",
    )
    assert "Secret Internal Project" not in query
    assert "deployment guidance" in query


def test_public_web_query_blocks_credentials():
    with pytest.raises(WebResearchPrivacyError):
        sanitize_public_web_query(
            proposed_query="look up this DATABASE_URL=postgresql://user:password@example.com/db",
            original_query="look up this DATABASE_URL=postgresql://user:password@example.com/db",
            selected_context_label=None,
        )


def test_framework_documentation_request_does_not_force_code_generation():
    profile = deterministic_request_profile(
        query="Search the web for the latest official Flask security documentation",
        route_intent="general_conversation",
        selected_context_type=None,
    )
    assert profile.needs_web is True
    assert profile.needs_code is False


def test_natural_language_percentage_does_not_use_partial_inline_expression():
    profile = deterministic_request_profile(
        query="What is 20% of 500?",
        route_intent="general_conversation",
        selected_context_type=None,
    )
    assert profile.needs_calculator is True
    assert profile.calculator_expression is None


def test_ai_profile_cannot_downgrade_explicit_mutation_or_scope(monkeypatch):
    from services import intelligence_capability_router_service as router

    monkeypatch.setattr(router, "get_ai_configuration", lambda: {
        "provider": "gemini", "api_key": "test", "model": "test-model"
    })
    monkeypatch.setattr(router, "_should_use_ai_profile", lambda *args, **kwargs: True)
    monkeypatch.setattr(router, "route_ai_text", lambda **kwargs: '''{
        "task_type": "explain",
        "complexity": "simple",
        "knowledge_scope": "general",
        "needs_workspace": false,
        "needs_rag": false,
        "needs_web": false,
        "needs_calculator": false,
        "needs_code": false,
        "action_mode": "read_only"
    }''')

    profile = router.understand_request(
        query="Create a task for this fix",
        route_intent="project_advice",
        selected_context_type="project",
        selected_context_label="Private Project",
    )
    assert profile.action_mode == "mutation_requested"
    assert profile.task_type == "execute"
    assert profile.complexity == "multi_step"
    assert profile.needs_workspace is True


def test_ai_profile_cannot_invent_mutation_intent(monkeypatch):
    from services import intelligence_capability_router_service as router

    monkeypatch.setattr(router, "get_ai_configuration", lambda: {
        "provider": "gemini", "api_key": "test", "model": "test-model"
    })
    monkeypatch.setattr(router, "_should_use_ai_profile", lambda *args, **kwargs: True)
    monkeypatch.setattr(router, "route_ai_text", lambda **kwargs: '''{
        "task_type": "execute",
        "complexity": "multi_step",
        "knowledge_scope": "general",
        "needs_workspace": false,
        "needs_rag": false,
        "needs_web": false,
        "needs_calculator": false,
        "needs_code": false,
        "action_mode": "mutation_requested"
    }''')

    profile = router.understand_request(
        query="Explain binary search",
        route_intent="general_conversation",
        selected_context_type=None,
        allow_ai=True,
    )
    assert profile.action_mode == "read_only"


def test_web_research_requires_attributable_sources(monkeypatch):
    from types import SimpleNamespace
    from services import web_research_service as web

    monkeypatch.setenv("ASK_LIFEOS_WEB_RESEARCH_ENABLED", "true")
    monkeypatch.setattr(web, "get_ai_configuration", lambda: {
        "provider": "gemini", "api_key": "test", "model": "test-model"
    })
    monkeypatch.setattr(web, "route_web_research", lambda **kwargs: SimpleNamespace(
        text="Current information with no evidence.",
        sources=(),
        search_queries=(),
    ))

    with pytest.raises(web.WebResearchError, match="attributable"):
        web.research_public_web(
            query="latest Flask release",
            original_query="latest Flask release",
        )


def test_explanation_with_python_code_and_equations_requests_code_not_web():
    profile = deterministic_request_profile(
        query="Explain binary search with Python code and complexity equations",
        route_intent="general_conversation",
        selected_context_type=None,
    )
    assert profile.task_type == "explain"
    assert profile.needs_code is True
    assert profile.needs_web is False
    assert profile.action_mode == "read_only"


@pytest.mark.parametrize(
    "secret_query",
    [
        "Search the web using OPENAI_API_KEY=sk-test-private-value-123456",
        "Look this up GEMINI_API_KEY=AIzaDefinitelyPrivateCredential12345",
        "Research DB_URL=postgresql://user:password@private.example/db",
        "Search JWT_SECRET=do-not-send-this-value",
    ],
)
def test_public_web_query_blocks_common_environment_secret_assignments(secret_query: str):
    with pytest.raises(WebResearchPrivacyError):
        sanitize_public_web_query(
            proposed_query=secret_query,
            original_query=secret_query,
            selected_context_label="Private Project",
        )


def test_public_web_source_url_rejects_internal_and_credentialed_targets():
    from services.web_research_service import _safe_public_url

    assert _safe_public_url("https://example.com/docs") == "https://example.com/docs"
    assert _safe_public_url("http://localhost:8000/admin") is None
    assert _safe_public_url("http://127.0.0.1/private") is None
    assert _safe_public_url("http://10.0.0.10/internal") is None
    assert _safe_public_url("http://169.254.169.254/latest/meta-data") is None
    assert _safe_public_url("https://user:password@example.com/private") is None


def test_public_web_privacy_rejects_before_provider_call(monkeypatch):
    from services import web_research_service as web

    provider_called = False

    def fake_route_web_research(**kwargs):
        nonlocal provider_called
        provider_called = True
        raise AssertionError("provider must not receive secret-bearing query")

    monkeypatch.setenv("ASK_LIFEOS_WEB_RESEARCH_ENABLED", "true")
    monkeypatch.setattr(web, "route_web_research", fake_route_web_research)

    with pytest.raises(web.WebResearchPrivacyError):
        web.research_public_web(
            query="Search current pricing DATABASE_URL=postgresql://u:p@example.com/db",
            original_query="Search current pricing DATABASE_URL=postgresql://u:p@example.com/db",
            selected_context_label="Private Project",
        )
    assert provider_called is False

def test_reasoning_json_parser_tolerates_harmless_provider_wrapper_text():
    from services.intelligence_reasoning_service import _parse_json_object

    parsed = _parse_json_object(
        'Here is the JSON you requested:\n'
        '{"answer":"Use a staged deployment.","factual_claims":[],"inferences":[],'
        '"recommendations":[{"text":"Use staging first.","supporting_fact_keys":[],'
        '"supporting_signal_titles":[]}],"document_claims":[],"web_claims":[],'
        '"general_claims":[]}'
    )
    assert parsed["answer"] == "Use a staged deployment."


def test_verifier_json_parser_tolerates_harmless_provider_wrapper_text():
    from services.intelligence_claim_verifier_service import _parse_verifier_response

    verified, issues = _parse_verifier_response(
        'Verification result:\n{"verified": true, "issues": []}\nDone.'
    )
    assert verified is True
    assert issues == ()

def test_advisory_fallback_only_surfaces_query_relevant_review_signals():
    from types import SimpleNamespace
    from services.intelligence_ask_service import _query_relevant_review_titles

    review = SimpleNamespace(
        signals=[
            SimpleNamespace(
                title="Overdue task: Run manual deployment-goal review",
                detail="Deployment readiness needs review.",
            ),
            SimpleNamespace(
                title="Overdue task: Design goal database schema",
                detail="Schema design work is late.",
            ),
            SimpleNamespace(
                title="Overdue task: Verify create-task confirmation",
                detail="I9 confirmation work is late.",
            ),
        ]
    )

    titles = _query_relevant_review_titles(
        query="What should I do to deploy this project?",
        review=review,
    )
    assert titles == ["Overdue task: Run manual deployment-goal review"]


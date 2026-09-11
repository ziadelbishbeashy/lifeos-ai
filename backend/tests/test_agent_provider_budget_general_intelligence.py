from services.agent_runtime_service import AGENT_LIMITS, _provider_call_cost_for_tool


def test_agent_provider_budget_counts_provider_backed_read_only_tools():
    assert AGENT_LIMITS["max_provider_calls"] == 4
    assert _provider_call_cost_for_tool("knowledge.ask_context") == 2
    assert _provider_call_cost_for_tool("public.web_search") == 1
    assert _provider_call_cost_for_tool("project.get_summary") == 0
    # Knowledge Ask + public web + final reasoner fits exactly in the bounded budget.
    assert 2 + 1 + 1 <= AGENT_LIMITS["max_provider_calls"]

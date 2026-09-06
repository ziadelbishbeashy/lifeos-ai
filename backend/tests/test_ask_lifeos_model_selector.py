from __future__ import annotations


def _login(client):
    return client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "StrongPass123!"},
    )


def test_ask_api_accepts_friendly_model_tier_and_returns_public_reasoning_tier(client, user):
    assert _login(client).status_code == 200
    response = client.post(
        "/api/v1/intelligence/ask",
        json={"query": "Which tasks are overdue?", "model_tier": "balanced"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["reasoning_tier"] == "normal"
    assert "model_tier" not in payload
    # This deterministic question should not require an LLM just because a tier
    # was selected; the model tier is only an override when provider work occurs.
    assert payload["response_mode"] == "deterministic_verified"


def test_ask_api_rejects_unknown_model_tier(client, user):
    assert _login(client).status_code == 200
    response = client.post(
        "/api/v1/intelligence/ask",
        json={"query": "Which tasks are overdue?", "model_tier": "ultra"},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert "fast" in str(payload).lower()
    assert "balanced" in str(payload).lower()
    assert "deep" in str(payload).lower()

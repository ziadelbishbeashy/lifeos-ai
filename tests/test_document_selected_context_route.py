"""Route contract for passing selected PDF context to Ask Document."""

from types import SimpleNamespace


def _login(client):
    return client.post(
        "/login",
        data={
            "email": "student@example.com",
            "password": "StrongPass123!",
        },
        follow_redirects=True,
    )


def test_question_route_passes_selected_context(app, client, user, monkeypatch):
    from routes import document_routes

    captured = {}

    def fake_ask(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            reused_existing=False,
        )

    monkeypatch.setattr(
        document_routes,
        "ask_owned_document",
        fake_ask,
    )

    _login(client)

    response = client.post(
        "/documents/1/questions",
        data={
            "question": "Why is this important?",
            "selected_context_text": "Ownership is checked before access.",
            "selected_context_page": "8",
            "selected_context_section": "Privacy",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert captured["selected_context_text"] == "Ownership is checked before access."
    assert captured["selected_context_page"] == "8"
    assert captured["selected_context_section"] == "Privacy"

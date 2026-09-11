"""Route tests for the reader-facing semantic PDF search API."""

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


def test_semantic_pdf_search_route_returns_reader_safe_payload(
    app,
    client,
    user,
    monkeypatch,
):
    from routes import document_routes

    monkeypatch.setattr(
        document_routes,
        "search_owned_document_for_pdf",
        lambda **kwargs: SimpleNamespace(
            as_dict=lambda: {
                "query": "privacy",
                "result_count": 2,
                "limited": False,
                "degraded": False,
                "matches": [
                    {
                        "match_id": "match-1",
                        "page_start": 8,
                        "page_end": 8,
                        "page_label": "8",
                        "section": "Privacy",
                        "text": "Private data remains protected.",
                        "emphasis": "strong",
                    }
                ],
            }
        ),
    )

    _login(client)

    response = client.get(
        "/documents/1/semantic-search?q=privacy"
    )

    assert response.status_code == 200

    payload = response.get_json()

    assert payload["ok"] is True
    assert payload["matches"][0]["page_start"] == 8

    serialized = str(payload)

    assert "chunk_id" not in serialized
    assert "semantic_score" not in serialized
    assert "retrieval_mode" not in serialized

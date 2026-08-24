"""Architecture contract for the fully separated React frontend."""

from __future__ import annotations


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "StrongPass123!"},
    )
    assert response.status_code == 200


def test_meta_reports_native_separated_frontend(client):
    response = client.get("/api/v1/meta")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["frontend_architecture"] == "react-native-full-separation"
    assert "document-analysis" in payload["native_frontend_slices"]
    assert "project-rag" in payload["native_frontend_slices"]


def test_legacy_proxy_is_not_registered(client):
    response = client.get("/api/v1/legacy-proxy")
    assert response.status_code == 404
    response = client.get("/api/v1/legacy-proxy/meta")
    assert response.status_code == 404


def test_session_boundary_is_json(client):
    response = client.get("/api/v1/session")
    assert response.status_code == 200
    assert response.is_json
    assert response.get_json()["authenticated"] is False


def test_authenticated_frontend_data_comes_from_api(client, user):
    _login(client)
    projects = client.get("/api/v1/projects")
    documents = client.get("/api/v1/documents")
    assert projects.status_code == 200
    assert documents.status_code == 200
    assert projects.is_json
    assert documents.is_json

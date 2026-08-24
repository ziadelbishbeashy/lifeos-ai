"""Read-only API v1 smoke tests."""

from app import create_app


def test_api_v1_health():
    app = create_app("testing")
    client = app.test_client()
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.get_json()["api"] == "v1"


def test_api_v1_meta_exposes_foundation_v2():
    app = create_app("testing")
    client = app.test_client()
    response = client.get("/api/v1/meta")
    assert response.status_code == 200
    assert response.get_json()["architecture"] == "foundation-v2"

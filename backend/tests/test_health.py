"""Deployment health endpoint tests."""


def test_liveness_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_readiness_endpoint(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.get_json()["database"] == "ok"

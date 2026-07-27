"""Application-factory smoke tests."""

from app import create_app


def test_application_factory_uses_testing_config():
    app = create_app("testing")

    assert app.config["TESTING"] is True
    assert app.config["DEBUG"] is False
    assert app.config["ENABLE_EMAIL_SCHEDULER"] is False


def test_health_endpoint():
    app = create_app("testing")
    client = app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "service": "lifeos",
    }

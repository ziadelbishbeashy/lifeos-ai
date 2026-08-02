"""Security regression tests."""

from app import create_app


def test_security_headers_are_present(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers.get("X-Request-ID")


def test_csrf_blocks_unprotected_post():
    app = create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": True,
            "SECRET_KEY": "testing-secret-key-that-is-long-enough",
        },
    )
    client = app.test_client()

    response = client.post(
        "/login",
        data={"email": "student@example.com", "password": "password"},
    )

    assert response.status_code == 400
    assert b"form expired" in response.data.lower()


def test_large_upload_has_friendly_error():
    app = create_app(
        "testing",
        {
            "MAX_CONTENT_LENGTH": 16,
            "WTF_CSRF_ENABLED": False,
        },
    )
    client = app.test_client()

    response = client.post(
        "/register",
        data={"name": "x" * 100},
        content_type="application/x-www-form-urlencoded",
    )

    assert response.status_code == 413
    assert b"too large" in response.data.lower()

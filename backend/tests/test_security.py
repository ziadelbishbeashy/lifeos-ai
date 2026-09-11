"""Security regression tests."""

import re

from app import create_app


def test_security_headers_are_present(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert response.headers["X-Permitted-Cross-Domain-Policies"] == "none"
    assert response.headers.get("X-Request-ID")


def test_trace_requests_are_rejected(client):
    response = client.open("/health", method="TRACE")

    assert response.status_code == 405


def test_untrusted_request_id_is_replaced(client):
    response = client.get("/health", headers={"X-Request-ID": "bad id with spaces"})

    request_id = response.headers["X-Request-ID"]
    assert request_id != "bad id with spaces"
    assert re.fullmatch(r"[0-9a-f]{24}", request_id)


def test_cross_site_unsafe_api_request_is_rejected_before_route_logic(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "not-important"},
        headers={
            "Origin": "https://evil.example",
            "Sec-Fetch-Site": "cross-site",
            "Accept": "application/json",
        },
    )

    assert response.status_code == 403


def test_same_hostname_with_different_scheme_is_not_same_origin():
    app = create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
        },
    )
    client = app.test_client()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "not-important"},
        headers={
            "Host": "localhost",
            "Origin": "https://localhost",
            "Accept": "application/json",
        },
    )

    assert response.status_code == 403


def test_api_json_body_has_smaller_limit_than_document_uploads():
    app = create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
            "MAX_CONTENT_LENGTH": 1024 * 1024,
            "MAX_API_JSON_BYTES": 64,
        },
    )
    client = app.test_client()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "x" * 200},
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 413


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


def test_explicit_trusted_proxy_origin_passes_origin_boundary():
    app = create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
            "TRUSTED_API_ORIGINS": ("http://localhost:5173",),
        },
    )
    client = app.test_client()

    # Unknown API route is intentional: 404 proves the security before_request
    # allowed the request to continue instead of returning 403.
    response = client.post(
        "/api/v1/security-boundary-probe",
        headers={
            "Host": "127.0.0.1:5000",
            "Origin": "http://localhost:5173",
            "Sec-Fetch-Site": "same-origin",
        },
    )

    assert response.status_code == 404


def test_trusted_origin_does_not_override_cross_site_fetch_metadata():
    app = create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
            "TRUSTED_API_ORIGINS": ("https://frontend.example",),
        },
    )
    client = app.test_client()

    response = client.post(
        "/api/v1/security-boundary-probe",
        headers={
            "Host": "api.example",
            "Origin": "https://frontend.example",
            "Sec-Fetch-Site": "cross-site",
        },
    )

    assert response.status_code == 403


def test_unlisted_proxy_origin_is_still_rejected():
    app = create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
            "TRUSTED_API_ORIGINS": ("http://localhost:5173",),
        },
    )
    client = app.test_client()

    response = client.post(
        "/api/v1/security-boundary-probe",
        headers={
            "Host": "127.0.0.1:5000",
            "Origin": "http://evil.local:5173",
            "Sec-Fetch-Site": "same-origin",
        },
    )

    assert response.status_code == 403


def test_allowed_hosts_accepts_host_with_port_without_request_hostname_attribute():
    app = create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
            "ALLOWED_HOSTS": ("127.0.0.1", "localhost"),
        },
    )
    client = app.test_client()

    response = client.get("/health", headers={"Host": "127.0.0.1:5000"})

    assert response.status_code == 200


def test_allowed_hosts_still_rejects_unlisted_host():
    app = create_app(
        "testing",
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
            "ALLOWED_HOSTS": ("127.0.0.1", "localhost"),
        },
    )
    client = app.test_client()

    response = client.get("/health", headers={"Host": "evil.example:5000"})

    assert response.status_code == 403

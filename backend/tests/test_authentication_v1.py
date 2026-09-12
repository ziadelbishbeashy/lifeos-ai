from __future__ import annotations

from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from database import db
from models import User, UserAuthIdentity, UserAuthSession, UserAuthToken
from services.auth_security_service import GoogleIdentityConflictError, create_or_link_google_user


def _login(client, *, email="student@example.com", password="StrongPass123!", remember=False):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "remember": remember},
    )


def test_api_login_creates_revocable_server_session_and_logout_revokes(app, client, user):
    response = _login(client, remember=True)
    assert response.status_code == 200, response.get_json()

    with app.app_context():
        rows = UserAuthSession.query.filter_by(user_id=user).all()
        assert len(rows) == 1
        assert rows[0].remember is True
        assert rows[0].revoked_at is None
        session_id = rows[0].id

    state = client.get("/api/v1/session")
    assert state.status_code == 200
    assert state.get_json()["authenticated"] is True

    logged_out = client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 200
    with app.app_context():
        assert db.session.get(UserAuthSession, session_id).revoked_at is not None


def test_deleted_or_revoked_server_session_invalidates_browser_cookie(app, client, user):
    assert _login(client).status_code == 200
    with app.app_context():
        row = UserAuthSession.query.filter_by(user_id=user, revoked_at=None).one()
        row.revoked_at = datetime.utcnow()
        db.session.commit()

    state = client.get("/api/v1/session")
    assert state.status_code == 200
    assert state.get_json() == {"authenticated": False, "user": None}


def test_login_rate_limit_blocks_repeated_password_guesses(app, client, user):
    app.config.update(AUTH_RATE_MAX_ATTEMPTS=3, AUTH_RATE_WINDOW_MINUTES=15, AUTH_RATE_BLOCK_MINUTES=15)
    for _ in range(3):
        response = _login(client, password="wrong-password")
        assert response.status_code == 401
    blocked = _login(client, password="wrong-password")
    assert blocked.status_code == 429
    assert blocked.get_json()["error"] == "rate_limited"


def test_password_recovery_is_non_enumerating_single_use_and_revokes_sessions(app, client, user, monkeypatch):
    monkeypatch.setattr("services.auth_email_service.send_email", lambda *args, **kwargs: True)
    app.config["AUTH_DEV_EXPOSE_TOKENS"] = True

    assert _login(client).status_code == 200

    known = client.post("/api/v1/auth/forgot-password", json={"email": "student@example.com"})
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert known.status_code == 202
    assert unknown.status_code == 202
    assert known.get_json()["message"] == unknown.get_json()["message"]
    token = known.get_json()["debug_token"]

    reset_client = app.test_client()
    reset = reset_client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "password": "NewStrongPass123!", "confirm_password": "NewStrongPass123!"},
    )
    assert reset.status_code == 200, reset.get_json()

    reused = reset_client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "password": "AnotherPass123!", "confirm_password": "AnotherPass123!"},
    )
    assert reused.status_code == 400
    assert reused.get_json()["error"] == "invalid_token"

    # The old authenticated browser is invalid after reset.
    assert client.get("/api/v1/session").get_json()["authenticated"] is False
    assert _login(reset_client, password="NewStrongPass123!").status_code == 200


def test_email_verification_is_one_time(app, client, user, monkeypatch):
    monkeypatch.setattr("services.auth_email_service.send_email", lambda *args, **kwargs: True)
    app.config["AUTH_DEV_EXPOSE_TOKENS"] = True
    assert _login(client).status_code == 200

    issued = client.post("/api/v1/auth/email-verification/request")
    assert issued.status_code == 202
    token = issued.get_json()["debug_token"]

    confirm = client.post("/api/v1/auth/email-verification/confirm", json={"token": token})
    assert confirm.status_code == 200
    with app.app_context():
        assert db.session.get(User, user).email_verified_at is not None

    second = client.post("/api/v1/auth/email-verification/confirm", json={"token": token})
    assert second.status_code == 400


def test_sensitive_action_freshness_uses_server_session_creation_time(app, user):
    client = app.test_client()
    assert _login(client).status_code == 200

    with app.app_context():
        row = UserAuthSession.query.filter_by(user_id=user, revoked_at=None).one()
        row.created_at = datetime(2000, 1, 1)
        db.session.commit()

    denied = client.post(
        "/api/v1/auth/password/change",
        json={
            "current_password": "StrongPass123!",
            "password": "ChangedPass123!",
            "confirm_password": "ChangedPass123!",
        },
    )
    assert denied.status_code == 401
    assert denied.get_json()["error"] == "reauthentication_required"


def test_change_password_revokes_other_sessions_but_keeps_current(app, user):
    first = app.test_client()
    second = app.test_client()
    assert _login(first).status_code == 200
    assert _login(second, remember=True).status_code == 200

    changed = first.post(
        "/api/v1/auth/password/change",
        json={
            "current_password": "StrongPass123!",
            "password": "ChangedPass123!",
            "confirm_password": "ChangedPass123!",
        },
    )
    assert changed.status_code == 200, changed.get_json()
    assert first.get("/api/v1/session").get_json()["authenticated"] is True
    assert second.get("/api/v1/session").get_json()["authenticated"] is False


def test_google_existing_gmail_account_can_be_linked_by_verified_subject(app, user):
    with app.app_context():
        account = db.session.get(User, user)
        account.email = "student@gmail.com"
        db.session.commit()
        linked, created = create_or_link_google_user(
            claims={
                "sub": "google-subject-123",
                "email": "student@gmail.com",
                "email_verified": True,
                "name": "Test Student",
            }
        )
        assert created is False
        assert linked.id == user
        identity = UserAuthIdentity.query.filter_by(user_id=user, provider="google").one()
        assert identity.provider_subject == "google-subject-123"
        assert linked.email_verified_at is not None


def test_google_third_party_email_requires_explicit_link_for_existing_account(app, user):
    with app.app_context():
        with pytest.raises(GoogleIdentityConflictError):
            create_or_link_google_user(
                claims={
                    "sub": "google-subject-thirdparty",
                    "email": "student@example.com",
                    "email_verified": True,
                    "name": "Test Student",
                }
            )


def test_google_start_uses_state_nonce_and_pkce(app, client):
    app.config.update(
        GOOGLE_OAUTH_CLIENT_ID="client-id.apps.googleusercontent.com",
        GOOGLE_OAUTH_CLIENT_SECRET="test-secret",
        GOOGLE_OAUTH_REDIRECT_URI="http://127.0.0.1:5000/api/v1/auth/google/callback",
    )
    response = client.post("/api/v1/auth/google/start", json={"next": "/planner"})
    assert response.status_code == 200
    target = urlsplit(response.get_json()["authorization_url"])
    assert target.netloc == "accounts.google.com"
    params = parse_qs(target.query)
    assert params["scope"] == ["openid email profile"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["state"][0]
    assert params["nonce"][0]
    assert params["code_challenge"][0]

    with client.session_transaction() as browser_session:
        stored = browser_session["vspace_google_oauth"]
        assert stored["state"] == params["state"][0]
        assert stored["next"] == "/planner"
        assert stored["verifier"] not in response.get_json()["authorization_url"]


def test_google_callback_creates_google_only_account_without_storing_oauth_tokens(app, client, monkeypatch):
    app.config.update(
        GOOGLE_OAUTH_CLIENT_ID="client-id.apps.googleusercontent.com",
        GOOGLE_OAUTH_CLIENT_SECRET="test-secret",
        GOOGLE_OAUTH_REDIRECT_URI="http://127.0.0.1:5000/api/v1/auth/google/callback",
        FRONTEND_BASE_URL="http://127.0.0.1:5173",
    )
    start = client.post("/api/v1/auth/google/start", json={"next": "/dashboard"})
    authorization_url = start.get_json()["authorization_url"]
    state = parse_qs(urlsplit(authorization_url).query)["state"][0]
    nonce = parse_qs(urlsplit(authorization_url).query)["nonce"][0]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id_token": "signed-google-id-token", "access_token": "must-not-be-stored", "refresh_token": "must-not-be-stored"}

    monkeypatch.setattr("lifeos.api.v1.auth_security.requests.post", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(
        "lifeos.api.v1.auth_security.google_id_token.verify_oauth2_token",
        lambda *args, **kwargs: {
            "sub": "new-google-user-sub",
            "email": "newuser@gmail.com",
            "email_verified": True,
            "name": "New Google User",
            "nonce": nonce,
        },
    )

    callback = client.get(f"/api/v1/auth/google/callback?code=one-time-code&state={state}")
    assert callback.status_code == 302
    assert callback.headers["Location"].startswith("http://127.0.0.1:5173/onboarding")

    with app.app_context():
        account = User.query.filter_by(email="newuser@gmail.com").one()
        assert account.password_hash is None
        assert account.email_verified_at is not None
        identity = UserAuthIdentity.query.filter_by(user_id=account.id, provider="google").one()
        assert identity.provider_subject == "new-google-user-sub"
        # Schema intentionally has no access/refresh-token columns.
        assert not hasattr(identity, "access_token")
        assert not hasattr(identity, "refresh_token")
        assert UserAuthToken.query.filter_by(user_id=account.id).count() == 0
        assert UserAuthSession.query.filter_by(user_id=account.id, auth_method="google").count() == 1

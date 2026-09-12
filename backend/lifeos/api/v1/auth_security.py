"""V-SPACE Authentication V1 recovery, Google sign-in and account security API."""

from __future__ import annotations

import secrets
import time
from urllib.parse import urlencode

import requests
from flask import Blueprint, current_app, jsonify, redirect, request, session
from flask_login import current_user
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token as google_id_token

from lifeos.api.v1.common import api_auth_required, json_body
from services.auth_email_service import send_email_verification, send_password_reset_email
from services.auth_security_service import (
    GOOGLE_OAUTH_SESSION_KEY,
    AuthSecurityError,
    GoogleIdentityConflictError,
    InvalidAuthTokenError,
    auth_rate_limit_is_blocked,
    auth_security_payload,
    build_google_pkce,
    change_password_for_user,
    clear_auth_failures,
    consume_email_verification_token,
    create_or_link_google_user,
    current_auth_session_record,
    disconnect_google_identity,
    establish_authenticated_session,
    record_auth_failure,
    reset_password_with_token,
    revoke_all_user_sessions,
)
from services.auth_service import find_user_by_email, normalize_email
from services.experience_profile_service import user_experience_payload


auth_security_api_bp = Blueprint("api_v1_auth_security", __name__, url_prefix="/api/v1/auth")


def _safe_next(value: str | None, default: str = "/dashboard") -> str:
    target = str(value or "").strip()
    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        return default
    return target[:1000]


def _frontend_redirect(path: str, **params):
    base = str(current_app.config.get("FRONTEND_BASE_URL") or current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
    query = urlencode({key: value for key, value in params.items() if value is not None})
    return redirect(f"{base}{path}{'?' + query if query else ''}")


def _google_redirect_uri() -> str:
    configured = str(current_app.config.get("GOOGLE_OAUTH_REDIRECT_URI") or "").strip()
    if configured:
        return configured
    # Use the browser-facing origin. In local development Vite proxies /api to
    # Flask, so the OAuth callback must return through :5173 to receive the same
    # host-only session cookie that stored state/nonce/PKCE verifier.
    return str(current_app.config.get("FRONTEND_BASE_URL") or current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/") + "/api/v1/auth/google/callback"


def _google_enabled() -> bool:
    return bool(
        str(current_app.config.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
        and str(current_app.config.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    )


def _fresh_required():
    """Require a recently established, revocable V-SPACE server session.

    Flask-Login's private ``_fresh`` flag is deliberately not used here. With
    strong session protection it may be downgraded independently of our
    server-side session, which caused freshly logged-in users to be rejected.

    Sensitive-action freshness is instead anchored to the creation time of the
    active ``UserAuthSession`` record. That record is opaque-token backed,
    revocable, user-bound, expiry checked on every authenticated request, and
    rotated after password changes.
    """
    if not current_user.is_authenticated:
        return jsonify({"error": "authentication_required", "message": "Please log in again."}), 401

    row = current_auth_session_record()
    if row is None or row.revoked_at is not None:
        return jsonify({"error": "reauthentication_required", "message": "For your security, log in again before changing account security."}), 401

    try:
        if int(row.user_id) != int(current_user.id):
            return jsonify({"error": "reauthentication_required", "message": "For your security, log in again before changing account security."}), 401
    except (TypeError, ValueError):
        return jsonify({"error": "reauthentication_required", "message": "For your security, log in again before changing account security."}), 401

    from datetime import datetime, timedelta

    created_at = row.created_at
    max_age = timedelta(minutes=max(1, int(current_app.config.get("AUTH_SENSITIVE_ACTION_MINUTES") or 30)))
    if created_at is None or created_at + max_age <= datetime.utcnow():
        return jsonify({"error": "reauthentication_required", "message": "For your security, log in again before changing account security."}), 401
    return None


@auth_security_api_bp.get("/config")
def auth_public_config():
    return jsonify({"google_enabled": _google_enabled()})


@auth_security_api_bp.post("/forgot-password")
def forgot_password():
    payload = json_body()
    email = normalize_email(payload.get("email"))
    generic = {
        "accepted": True,
        "message": "If an account exists for this email, password-reset instructions will be sent.",
    }
    if auth_rate_limit_is_blocked(purpose="password_reset", identity=email):
        return jsonify(generic), 202

    # Count every recovery request (known or unknown account) so this endpoint
    # cannot be used to spam a real user's inbox.
    record_auth_failure(purpose="password_reset", identity=email)
    user = find_user_by_email(email)
    debug_token = None
    if user is not None:
        try:
            issued = send_password_reset_email(user)
            if current_app.config.get("AUTH_DEV_EXPOSE_TOKENS") and current_app.config.get("ENV_NAME") != "production":
                debug_token = issued.raw_token
        except Exception:
            # Recovery must not expose account existence or mail-provider state.
            current_app.logger.exception("V-SPACE password reset email delivery failed.")
    if debug_token:
        generic["debug_token"] = debug_token
    return jsonify(generic), 202


@auth_security_api_bp.post("/reset-password")
def reset_password():
    payload = json_body()
    try:
        reset_password_with_token(
            raw_token=str(payload.get("token") or ""),
            password=str(payload.get("password") or ""),
            confirm_password=str(payload.get("confirm_password") or ""),
        )
    except InvalidAuthTokenError as error:
        return jsonify({"error": "invalid_token", "message": str(error)}), 400
    except ValueError as error:
        return jsonify({"error": "validation_error", "message": str(error)}), 400
    return jsonify({"reset": True, "message": "Your password has been reset. Sign in with your new password."})


@auth_security_api_bp.post("/email-verification/request")
@api_auth_required
def request_email_verification():
    if current_user.email_verified_at is not None:
        return jsonify({"accepted": True, "verified": True, "message": "Your email is already verified."})
    if auth_rate_limit_is_blocked(purpose="email_verify", identity=current_user.email):
        return jsonify({"accepted": True, "verified": False, "message": "If delivery is available, a verification email will be sent."}), 202
    record_auth_failure(purpose="email_verify", identity=current_user.email)
    debug_token = None
    try:
        issued = send_email_verification(current_user)
        if current_app.config.get("AUTH_DEV_EXPOSE_TOKENS") and current_app.config.get("ENV_NAME") != "production":
            debug_token = issued.raw_token
    except Exception:
        current_app.logger.exception("V-SPACE verification email delivery failed.")
    response = {"accepted": True, "verified": False, "message": "If delivery is available, a verification email will be sent."}
    if debug_token:
        response["debug_token"] = debug_token
    return jsonify(response), 202


@auth_security_api_bp.post("/email-verification/confirm")
def confirm_email_verification():
    payload = json_body()
    try:
        user = consume_email_verification_token(raw_token=str(payload.get("token") or ""))
    except InvalidAuthTokenError as error:
        return jsonify({"error": "invalid_token", "message": str(error)}), 400
    return jsonify({"verified": True, "email": user.email})


@auth_security_api_bp.get("/security")
@api_auth_required
def account_security():
    return jsonify({"security": auth_security_payload(user=current_user)})


@auth_security_api_bp.post("/password/change")
@api_auth_required
def change_password():
    fresh_error = _fresh_required()
    if fresh_error:
        return fresh_error
    payload = json_body()
    try:
        user = current_user._get_current_object()
        current_row = current_auth_session_record()
        remember = bool(current_row.remember) if current_row is not None else bool(session.permanent)
        change_password_for_user(
            user=user,
            current_password=payload.get("current_password"),
            password=str(payload.get("password") or ""),
            confirm_password=str(payload.get("confirm_password") or ""),
        )
        # change_password_for_user revokes every pre-change server session in the
        # same transaction as the password update. Issue one fresh token only for
        # this browser after that secure commit succeeds.
        new_session = establish_authenticated_session(user=user, remember=remember, auth_method="password")
        # Defense in depth: after rotation, enforce that no pre-change browser
        # session remains active even if another worker/client had a stale ORM
        # identity loaded. The newly issued current session is the sole exception.
        revoke_all_user_sessions(user_id=int(user.id), except_session_id=int(new_session.id))
    except ValueError as error:
        return jsonify({"error": "validation_error", "message": str(error)}), 400
    except AuthSecurityError as error:
        current_app.logger.exception("V-SPACE password change failed securely.")
        return jsonify({"error": "password_change_failed", "message": str(error)}), 503
    return jsonify({"changed": True, "message": "Password updated. Your current session was rotated and other sessions were signed out."})


@auth_security_api_bp.post("/sessions/revoke-others")
@api_auth_required
def revoke_other_sessions():
    fresh_error = _fresh_required()
    if fresh_error:
        return fresh_error
    current_row = current_auth_session_record()
    count = revoke_all_user_sessions(user_id=current_user.id, except_session_id=current_row.id if current_row else None)
    return jsonify({"revoked": count})


@auth_security_api_bp.delete("/sessions/<int:session_id>")
@api_auth_required
def revoke_session(session_id: int):
    from models import UserAuthSession

    row = UserAuthSession.query.filter_by(id=int(session_id), user_id=int(current_user.id), revoked_at=None).first()
    if row is None:
        return jsonify({"error": "not_found", "message": "Session not found."}), 404
    current_row = current_auth_session_record()
    if current_row is not None and int(current_row.id) == int(row.id):
        return jsonify({"error": "current_session", "message": "Use Log out to end your current session."}), 400
    from datetime import datetime
    row.revoked_at = datetime.utcnow()
    from database import db
    db.session.commit()
    return jsonify({"revoked": True})


@auth_security_api_bp.post("/google/start")
def google_start():
    if not _google_enabled():
        return jsonify({"error": "google_not_configured", "message": "Google sign-in is not configured yet."}), 503

    payload = json_body()
    mode = str(payload.get("mode") or "login").strip().lower()
    if mode not in {"login", "link"}:
        mode = "login"
    if mode == "link":
        fresh_error = _fresh_required()
        if fresh_error:
            return fresh_error

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier, challenge = build_google_pkce()
    next_path = _safe_next(payload.get("next"), "/dashboard")
    session[GOOGLE_OAUTH_SESSION_KEY] = {
        "state": state,
        "nonce": nonce,
        "verifier": verifier,
        "started_at": int(time.time()),
        "next": next_path,
        "mode": mode,
        "link_user_id": int(current_user.id) if mode == "link" and current_user.is_authenticated else None,
    }

    query = urlencode({
        "client_id": current_app.config["GOOGLE_OAUTH_CLIENT_ID"],
        "redirect_uri": _google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    })
    return jsonify({"authorization_url": f"{current_app.config['GOOGLE_OAUTH_AUTHORIZE_URL']}?{query}"})


@auth_security_api_bp.get("/google/callback")
def google_callback():
    oauth_state = session.pop(GOOGLE_OAUTH_SESSION_KEY, None)
    if not isinstance(oauth_state, dict):
        return _frontend_redirect("/login", google_error="Google sign-in expired. Please try again.")
    if request.args.get("error"):
        return _frontend_redirect("/login", google_error="Google sign-in was cancelled.")

    supplied_state = str(request.args.get("state") or "")
    if not secrets.compare_digest(str(oauth_state.get("state") or ""), supplied_state):
        return _frontend_redirect("/login", google_error="Google sign-in could not be verified.")
    if int(time.time()) - int(oauth_state.get("started_at") or 0) > 600:
        return _frontend_redirect("/login", google_error="Google sign-in expired. Please try again.")

    code = str(request.args.get("code") or "")
    if not code:
        return _frontend_redirect("/login", google_error="Google did not return a sign-in code.")

    try:
        token_response = requests.post(
            str(current_app.config["GOOGLE_OAUTH_TOKEN_URL"]),
            data={
                "code": code,
                "client_id": current_app.config["GOOGLE_OAUTH_CLIENT_ID"],
                "client_secret": current_app.config["GOOGLE_OAUTH_CLIENT_SECRET"],
                "redirect_uri": _google_redirect_uri(),
                "grant_type": "authorization_code",
                "code_verifier": str(oauth_state.get("verifier") or ""),
            },
            timeout=10,
            allow_redirects=False,
        )
        token_response.raise_for_status()
        token_payload = token_response.json()
        raw_id_token = str(token_payload.get("id_token") or "")
        claims = google_id_token.verify_oauth2_token(
            raw_id_token,
            GoogleAuthRequest(),
            audience=str(current_app.config["GOOGLE_OAUTH_CLIENT_ID"]),
        )
        if not secrets.compare_digest(str(claims.get("nonce") or ""), str(oauth_state.get("nonce") or "")):
            raise AuthSecurityError("Google nonce validation failed.")
    except Exception:
        current_app.logger.exception("V-SPACE Google sign-in validation failed.")
        return _frontend_redirect("/login", google_error="Google sign-in could not be verified.")

    mode = str(oauth_state.get("mode") or "login")
    linking_user = None
    if mode == "link":
        if not current_user.is_authenticated or int(current_user.id) != int(oauth_state.get("link_user_id") or -1):
            return _frontend_redirect("/login", google_error="Your session changed before Google could be connected.")
        linking_user = current_user._get_current_object()

    try:
        user, _created = create_or_link_google_user(claims=claims, linking_user=linking_user)
    except GoogleIdentityConflictError as error:
        target = "/settings" if mode == "link" and current_user.is_authenticated else "/login"
        return _frontend_redirect(target, google_error=str(error))
    except AuthSecurityError:
        current_app.logger.exception("V-SPACE could not resolve the Google identity.")
        return _frontend_redirect("/login", google_error="Google sign-in could not be completed.")

    if mode == "link":
        return _frontend_redirect("/settings", google_connected="1")

    clear_auth_failures(purpose="login", identity=user.email)
    establish_authenticated_session(user=user, remember=True, auth_method="google")
    next_path = _safe_next(oauth_state.get("next"), "/dashboard")
    experience = user_experience_payload(user)
    if not experience.get("onboarding_completed"):
        next_path = f"/onboarding?{urlencode({'next': next_path})}"
    return _frontend_redirect(next_path)


@auth_security_api_bp.post("/google/disconnect")
@api_auth_required
def google_disconnect():
    fresh_error = _fresh_required()
    if fresh_error:
        return fresh_error
    try:
        disconnected = disconnect_google_identity(user=current_user)
    except AuthSecurityError as error:
        return jsonify({"error": "unsafe_disconnect", "message": str(error)}), 400
    return jsonify({"disconnected": disconnected})

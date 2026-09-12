"""Security-sensitive authentication helpers for V-SPACE Authentication V1.

This module owns server-side session revocation, one-time auth tokens, auth
throttling, and Google identity linkage. Raw reset/session tokens are never
persisted. OAuth access/refresh tokens are never stored because V-SPACE only
uses Google for sign-in identity in this milestone.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from flask import current_app, request, session
from flask_login import current_user, login_user, logout_user
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from database import db
from models import (
    AuthRateLimitBucket,
    User,
    UserAuthIdentity,
    UserAuthSession,
    UserAuthToken,
)
from services.auth_service import normalize_email


AUTH_SESSION_KEY = "vspace_auth_session"
GOOGLE_OAUTH_SESSION_KEY = "vspace_google_oauth"
RESET_PURPOSE = "password_reset"
VERIFY_PURPOSE = "email_verification"


class AuthSecurityError(RuntimeError):
    pass


class InvalidAuthTokenError(AuthSecurityError, ValueError):
    pass


class AuthRateLimitedError(AuthSecurityError):
    pass


class GoogleIdentityConflictError(AuthSecurityError):
    pass


@dataclass(frozen=True)
class IssuedAuthToken:
    raw_token: str
    expires_at: datetime


def _utcnow() -> datetime:
    return datetime.utcnow()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _secret_digest(value: str) -> str:
    secret = str(current_app.config.get("SECRET_KEY") or "").encode("utf-8")
    return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()


def _client_ip_hash() -> str | None:
    raw = str(request.remote_addr or "").strip()
    return _secret_digest(f"ip:{raw}") if raw else None


def _bounded_user_agent() -> str | None:
    value = " ".join(str(request.headers.get("User-Agent") or "").split())[:320]
    return value or None


def _session_duration(*, remember: bool) -> timedelta:
    if remember:
        return timedelta(days=int(current_app.config.get("AUTH_REMEMBER_SESSION_DAYS") or 14))
    return timedelta(hours=int(current_app.config.get("AUTH_SESSION_HOURS") or 12))


def _idle_duration(*, remember: bool) -> timedelta:
    if remember:
        return timedelta(days=int(current_app.config.get("AUTH_REMEMBER_IDLE_DAYS") or 7))
    return timedelta(minutes=int(current_app.config.get("AUTH_SESSION_IDLE_MINUTES") or 120))


def current_auth_session_record() -> UserAuthSession | None:
    raw = str(session.get(AUTH_SESSION_KEY) or "")
    if not raw:
        return None
    return UserAuthSession.query.filter_by(token_hash=_sha256(raw)).first()


def establish_authenticated_session(
    *,
    user: User,
    remember: bool = False,
    auth_method: str = "password",
) -> UserAuthSession:
    """Rotate the browser session and create a revocable server-side record."""

    raw = secrets.token_urlsafe(32)
    now = _utcnow()
    row = UserAuthSession(
        user_id=int(user.id),
        token_hash=_sha256(raw),
        auth_method=str(auth_method or "password")[:24],
        remember=bool(remember),
        user_agent=_bounded_user_agent(),
        ip_hash=_client_ip_hash(),
        created_at=now,
        last_seen_at=now,
        expires_at=now + _session_duration(remember=bool(remember)),
    )
    db.session.add(row)
    db.session.commit()

    # Clear every pre-auth value, including stale CSRF and OAuth state. A fresh
    # CSRF token will be issued after login by the existing /api/v1/csrf route.
    session.clear()
    session.permanent = bool(remember)
    login_user(user, remember=False, fresh=True)
    session[AUTH_SESSION_KEY] = raw
    session["auth_method"] = row.auth_method
    session["auth_fresh_at"] = int(now.timestamp())
    return row


def revoke_current_authenticated_session() -> None:
    row = current_auth_session_record()
    if row is not None and row.revoked_at is None:
        row.revoked_at = _utcnow()
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
    logout_user()
    session.clear()


def _revoke_user_sessions_in_transaction(*, user_id: int, now: datetime, except_session_id: int | None = None) -> int:
    """Mark active auth sessions revoked with one database UPDATE.

    Using a set-based UPDATE avoids relying on already-loaded ORM instances when
    multiple browser clients are active during the same test/process. The caller
    controls the surrounding transaction so credential changes and revocation can
    remain atomic.
    """

    statement = (
        update(UserAuthSession)
        .where(UserAuthSession.user_id == int(user_id))
        .where(UserAuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    if except_session_id is not None:
        statement = statement.where(UserAuthSession.id != int(except_session_id))
    result = db.session.execute(statement.execution_options(synchronize_session=False))
    return int(result.rowcount or 0)


def revoke_all_user_sessions(*, user_id: int, except_session_id: int | None = None) -> int:
    now = _utcnow()
    try:
        count = _revoke_user_sessions_in_transaction(
            user_id=int(user_id),
            now=now,
            except_session_id=except_session_id,
        )
        db.session.commit()
        # Expire any UserAuthSession objects previously loaded in this worker so
        # subsequent validation observes the database revocation immediately.
        db.session.expire_all()
        return count
    except SQLAlchemyError as error:
        db.session.rollback()
        raise AuthSecurityError("V-SPACE could not revoke account sessions securely.") from error


def validate_browser_auth_session() -> bool:
    """Fail closed unless Flask-Login and the V-SPACE server session agree.

    ``current_user`` is deliberately resolved before inspecting the Flask
    session. Flask-Login loads identities lazily, so relying only on ``_user_id``
    can miss a restored/remembered identity until after a ``before_request``
    hook has already run. Every authenticated request must therefore prove both
    the Flask identity and the opaque V-SPACE server-session token.
    """

    # Force Flask-Login to resolve the request identity *now*, before we decide
    # whether this browser is allowed to remain authenticated.
    authenticated = bool(current_user.is_authenticated)
    if not authenticated:
        # A V-SPACE token without an authenticated Flask identity is stale.
        if session.get(AUTH_SESSION_KEY):
            session.clear()
        return True

    try:
        expected_user_id = int(current_user.id)
    except (TypeError, ValueError, AttributeError):
        logout_user()
        session.clear()
        return False

    raw = str(session.get(AUTH_SESSION_KEY) or "")
    if not raw:
        logout_user()
        session.clear()
        return False

    now = _utcnow()
    # Query only an active row owned by this exact user. A revoked token cannot
    # be resurrected by Flask-Login or a long-lived/permanent browser cookie.
    row = UserAuthSession.query.filter_by(
        token_hash=_sha256(raw),
        user_id=expected_user_id,
        revoked_at=None,
    ).first()

    expired = row is None or row.expires_at <= now
    idle = False
    if row is not None and not expired:
        idle = row.last_seen_at + _idle_duration(remember=bool(row.remember)) <= now

    if expired or idle:
        if row is not None and row.revoked_at is None:
            row.revoked_at = now
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
        logout_user()
        session.clear()
        return False

    touch_seconds = int(current_app.config.get("AUTH_SESSION_TOUCH_SECONDS") or 300)
    if (now - row.last_seen_at).total_seconds() >= max(60, touch_seconds):
        row.last_seen_at = now
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
    return True


def _rate_bucket_key(*, purpose: str, dimension: str, value: str) -> str:
    digest = _secret_digest(f"{purpose}:{dimension}:{value.casefold()}")
    return f"{purpose[:24]}:{dimension[:12]}:{digest[:48]}"


def _rate_limit_dimensions(identity: str | None) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    normalized = normalize_email(identity)
    if normalized:
        items.append(("identity", normalized))
    remote = str(request.remote_addr or "").strip()
    if remote:
        items.append(("ip", remote))
    return items


def auth_rate_limit_is_blocked(*, purpose: str, identity: str | None = None) -> bool:
    now = _utcnow()
    for dimension, value in _rate_limit_dimensions(identity):
        key = _rate_bucket_key(purpose=purpose, dimension=dimension, value=value)
        row = AuthRateLimitBucket.query.filter_by(bucket_key=key).first()
        if row is not None and row.blocked_until is not None and row.blocked_until > now:
            return True
    return False


def record_auth_failure(*, purpose: str, identity: str | None = None) -> None:
    now = _utcnow()
    window = timedelta(minutes=int(current_app.config.get("AUTH_RATE_WINDOW_MINUTES") or 15))
    block = timedelta(minutes=int(current_app.config.get("AUTH_RATE_BLOCK_MINUTES") or 15))
    max_attempts = int(current_app.config.get("AUTH_RATE_MAX_ATTEMPTS") or 8)

    for dimension, value in _rate_limit_dimensions(identity):
        key = _rate_bucket_key(purpose=purpose, dimension=dimension, value=value)
        row = AuthRateLimitBucket.query.filter_by(bucket_key=key).first()
        if row is None:
            row = AuthRateLimitBucket(bucket_key=key, window_started_at=now, attempts=0)
            db.session.add(row)
        if row.window_started_at + window <= now:
            row.window_started_at = now
            row.attempts = 0
            row.blocked_until = None
        row.attempts = int(row.attempts or 0) + 1
        if row.attempts >= max_attempts:
            row.blocked_until = now + block
        row.updated_at = now
    try:
        db.session.commit()
    except IntegrityError:
        # A concurrent first attempt can race the unique bucket insert. Fail
        # closed for this request without exposing internal state.
        db.session.rollback()
    except SQLAlchemyError:
        db.session.rollback()


def clear_auth_failures(*, purpose: str, identity: str | None = None) -> None:
    # A successful login clears only the account-specific failure bucket. The
    # source-IP bucket deliberately remains so one valid account cannot reset an
    # attacker's network-wide brute-force history.
    normalized = normalize_email(identity)
    if not normalized:
        return
    keys = [_rate_bucket_key(purpose=purpose, dimension="identity", value=normalized)]
    AuthRateLimitBucket.query.filter(AuthRateLimitBucket.bucket_key.in_(keys)).delete(synchronize_session=False)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()


def issue_user_auth_token(*, user: User, purpose: str, lifetime_minutes: int) -> IssuedAuthToken:
    if purpose not in {RESET_PURPOSE, VERIFY_PURPOSE}:
        raise ValueError("Unsupported authentication token purpose.")
    now = _utcnow()
    # Invalidate older unconsumed tokens for the same purpose so only the newest
    # email link remains useful.
    for row in UserAuthToken.query.filter_by(user_id=int(user.id), purpose=purpose, used_at=None).all():
        row.used_at = now

    raw = secrets.token_urlsafe(32)
    expires = now + timedelta(minutes=max(5, int(lifetime_minutes)))
    db.session.add(UserAuthToken(
        user_id=int(user.id),
        purpose=purpose,
        token_hash=_sha256(raw),
        expires_at=expires,
        created_at=now,
    ))
    db.session.commit()
    return IssuedAuthToken(raw_token=raw, expires_at=expires)


def require_valid_user_auth_token(*, raw_token: str, purpose: str) -> UserAuthToken:
    token = str(raw_token or "").strip()
    if len(token) < 32 or len(token) > 256:
        raise InvalidAuthTokenError("This security link is invalid or has expired.")
    row = UserAuthToken.query.filter_by(token_hash=_sha256(token), purpose=purpose).first()
    now = _utcnow()
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise InvalidAuthTokenError("This security link is invalid or has expired.")
    return row


def consume_email_verification_token(*, raw_token: str) -> User:
    row = require_valid_user_auth_token(raw_token=raw_token, purpose=VERIFY_PURPOSE)
    user = db.session.get(User, int(row.user_id))
    if user is None:
        raise InvalidAuthTokenError("This security link is invalid or has expired.")
    now = _utcnow()
    row.used_at = now
    if user.email_verified_at is None:
        user.email_verified_at = now
    db.session.commit()
    return user


def reset_password_with_token(*, raw_token: str, password: str, confirm_password: str) -> User:
    from services.auth_service import MAX_AUTH_PASSWORD_CHARACTERS

    new_password = str(password or "")
    if len(new_password) < 8:
        raise ValueError("Password must contain at least 8 characters.")
    if len(new_password) > MAX_AUTH_PASSWORD_CHARACTERS:
        raise ValueError(f"Password must contain at most {MAX_AUTH_PASSWORD_CHARACTERS} characters.")
    if new_password != str(confirm_password or ""):
        raise ValueError("The passwords do not match.")

    token_row = require_valid_user_auth_token(raw_token=raw_token, purpose=RESET_PURPOSE)
    user = db.session.get(User, int(token_row.user_id))
    if user is None:
        raise InvalidAuthTokenError("This security link is invalid or has expired.")
    now = _utcnow()
    user.set_password(new_password)
    if user.email_verified_at is None:
        user.email_verified_at = now
    token_row.used_at = now
    for other in UserAuthToken.query.filter_by(user_id=int(user.id), purpose=RESET_PURPOSE, used_at=None).all():
        other.used_at = now
    for auth_session in UserAuthSession.query.filter_by(user_id=int(user.id), revoked_at=None).all():
        auth_session.revoked_at = now
    db.session.commit()
    return user


def change_password_for_user(*, user: User, current_password: str | None, password: str, confirm_password: str) -> None:
    from services.auth_service import MAX_AUTH_PASSWORD_CHARACTERS

    if user.has_password and not user.check_password(str(current_password or "")):
        raise ValueError("Current password is incorrect.")
    new_password = str(password or "")
    if len(new_password) < 8:
        raise ValueError("Password must contain at least 8 characters.")
    if len(new_password) > MAX_AUTH_PASSWORD_CHARACTERS:
        raise ValueError(f"Password must contain at most {MAX_AUTH_PASSWORD_CHARACTERS} characters.")
    if new_password != str(confirm_password or ""):
        raise ValueError("The passwords do not match.")

    # Credential update and session revocation are committed together. If this
    # transaction fails, the old password/session state remains unchanged; if it
    # succeeds, every pre-change session token is already unusable before the
    # caller issues a replacement session for the current browser.
    now = _utcnow()
    user.set_password(new_password)
    try:
        _revoke_user_sessions_in_transaction(user_id=int(user.id), now=now)
        db.session.commit()
        # Ensure this worker cannot keep a stale in-memory session row marked as
        # active after the credential transaction commits.
        db.session.expire_all()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise AuthSecurityError("V-SPACE could not update your password securely.") from error


def google_identity_for_subject(subject: str) -> UserAuthIdentity | None:
    return UserAuthIdentity.query.filter_by(provider="google", provider_subject=str(subject)).first()


def google_is_authoritative_for_email(*, email: str, hosted_domain: str | None) -> bool:
    normalized = normalize_email(email)
    return normalized.endswith("@gmail.com") or bool(str(hosted_domain or "").strip())


def create_or_link_google_user(*, claims: dict[str, Any], linking_user: User | None = None) -> tuple[User, bool]:
    """Resolve a verified Google ID token to one V-SPACE user.

    Returns ``(user, created)``. Existing local accounts are auto-linked only
    when Google is authoritative for that email (Gmail/Workspace). Otherwise the
    user must sign in locally first and explicitly connect Google in Settings.
    """

    subject = str(claims.get("sub") or "").strip()
    email = normalize_email(claims.get("email"))
    verified = claims.get("email_verified") is True
    if not subject or not email or not verified:
        raise AuthSecurityError("Google did not provide a verified identity.")

    existing_identity = google_identity_for_subject(subject)
    if existing_identity is not None:
        user = db.session.get(User, int(existing_identity.user_id))
        if user is None:
            raise AuthSecurityError("The linked Google account is unavailable.")
        if linking_user is not None and int(user.id) != int(linking_user.id):
            raise GoogleIdentityConflictError("That Google account is already linked to another V-SPACE account.")
        existing_identity.provider_email = email
        existing_identity.updated_at = _utcnow()
        db.session.commit()
        return user, False

    if linking_user is not None:
        existing_for_user = UserAuthIdentity.query.filter_by(user_id=int(linking_user.id), provider="google").first()
        if existing_for_user is not None:
            raise GoogleIdentityConflictError("This V-SPACE account already has a Google sign-in connected.")
        user = linking_user
    else:
        user = User.query.filter_by(email=email).first()
        if user is not None and not google_is_authoritative_for_email(email=email, hosted_domain=claims.get("hd")):
            raise GoogleIdentityConflictError(
                "Sign in with your password first, then connect this Google account from Settings."
            )

    created = False
    now = _utcnow()
    if user is None:
        name = " ".join(str(claims.get("name") or "").split())[:120] or email.split("@", 1)[0][:120]
        user = User(name=name, email=email, password_hash=None)
        if google_is_authoritative_for_email(email=email, hosted_domain=claims.get("hd")):
            user.email_verified_at = now
        db.session.add(user)
        db.session.flush()
        created = True
    elif google_is_authoritative_for_email(email=email, hosted_domain=claims.get("hd")) and user.email_verified_at is None:
        user.email_verified_at = now

    db.session.add(UserAuthIdentity(
        user_id=int(user.id),
        provider="google",
        provider_subject=subject,
        provider_email=email,
        created_at=now,
        updated_at=now,
    ))
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise GoogleIdentityConflictError("That Google account could not be linked safely.") from error
    return user, created


def disconnect_google_identity(*, user: User) -> bool:
    identity = UserAuthIdentity.query.filter_by(user_id=int(user.id), provider="google").first()
    if identity is None:
        return False
    if not user.has_password:
        raise AuthSecurityError("Create a password before disconnecting your only sign-in method.")
    db.session.delete(identity)
    db.session.commit()
    return True


def session_device_label(user_agent: str | None) -> str:
    ua = str(user_agent or "")
    browser = "Browser"
    if "Edg/" in ua:
        browser = "Edge"
    elif "Chrome/" in ua:
        browser = "Chrome"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "Safari/" in ua and "Chrome/" not in ua:
        browser = "Safari"
    platform = "Web"
    if "Windows" in ua:
        platform = "Windows"
    elif "Macintosh" in ua:
        platform = "macOS"
    elif "iPhone" in ua:
        platform = "iPhone"
    elif "Android" in ua:
        platform = "Android"
    elif "Linux" in ua:
        platform = "Linux"
    return f"{browser} · {platform}"


def auth_security_payload(*, user: User) -> dict[str, Any]:
    current = current_auth_session_record()
    identities = UserAuthIdentity.query.filter_by(user_id=int(user.id)).all()
    rows = UserAuthSession.query.filter_by(user_id=int(user.id), revoked_at=None).order_by(UserAuthSession.last_seen_at.desc()).limit(20).all()
    return {
        "email": user.email,
        "email_verified": bool(user.email_verified_at),
        "email_verified_at": user.email_verified_at.isoformat() if user.email_verified_at else None,
        "has_password": bool(user.has_password),
        "google_available": bool(
            str(current_app.config.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
            and str(current_app.config.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
        ),
        "google_connected": any(row.provider == "google" for row in identities),
        "google_email": next((row.provider_email for row in identities if row.provider == "google"), None),
        "sessions": [
            {
                "id": int(row.id),
                "current": bool(current and int(current.id) == int(row.id)),
                "device": session_device_label(row.user_agent),
                "auth_method": row.auth_method,
                "remember": bool(row.remember),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            }
            for row in rows
            if row.expires_at > _utcnow()
        ],
    }


def build_google_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def init_auth_session_security(app) -> None:
    """Enforce revocable server-side auth sessions on every authenticated request."""

    @app.before_request
    def validate_vspace_auth_session():
        validate_browser_auth_session()

"""Authentication business rules for LifeOS.

Routes should remain responsible for HTTP concerns only.  This module owns
registration validation, account creation, legacy-project ownership, and
credential checks so the same behaviour can later be reused by APIs, social
login, and password-recovery workflows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from flask import current_app, has_app_context

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from database import db
from models import Project, User


_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MAX_AUTH_NAME_CHARACTERS = 120
MAX_AUTH_EMAIL_CHARACTERS = 320
MAX_AUTH_PASSWORD_CHARACTERS = 256

# Spend a normal password-hash verification even when an account does not exist.
# This reduces the usefulness of response-timing differences for email enumeration
# without ever storing or querying a real user's hash.
_DUMMY_PASSWORD_HASH = generate_password_hash("lifeos-auth-dummy-password-never-valid")


class DuplicateEmailError(ValueError):
    """Raised when an account already uses the requested email address."""


class AccountCreationError(RuntimeError):
    """Raised when an unexpected database error prevents registration."""


@dataclass(frozen=True)
class RegistrationInput:
    """Normalised registration values received from the public form."""

    name: str
    email: str
    password: str
    confirm_password: str


def normalize_email(email: str | None) -> str:
    """Return a stable, case-insensitive email value."""

    return (email or "").strip().casefold()


def build_registration_input(
    *,
    name: str | None,
    email: str | None,
    password: str | None,
    confirm_password: str | None,
) -> RegistrationInput:
    """Create a normalised registration object from form values."""

    return RegistrationInput(
        name=(name or "").strip(),
        email=normalize_email(email),
        password=password or "",
        confirm_password=confirm_password or "",
    )


def validate_registration(data: RegistrationInput) -> str | None:
    """Return a user-facing validation message, or ``None`` when valid."""

    if len(data.name) < 2:
        return "Please enter your full name."
    if len(data.name) > MAX_AUTH_NAME_CHARACTERS:
        return f"Name must contain at most {MAX_AUTH_NAME_CHARACTERS} characters."

    if len(data.email) > MAX_AUTH_EMAIL_CHARACTERS or not _EMAIL_PATTERN.fullmatch(data.email):
        return "Please enter a valid email address."

    if len(data.password) < 8:
        return "Password must contain at least 8 characters."
    if len(data.password) > MAX_AUTH_PASSWORD_CHARACTERS:
        return f"Password must contain at most {MAX_AUTH_PASSWORD_CHARACTERS} characters."

    if data.password != data.confirm_password:
        return "The passwords do not match."

    return None


def find_user_by_email(email: str | None) -> User | None:
    """Find an account using the normalised email address."""

    normalised = normalize_email(email)
    if not normalised or len(normalised) > MAX_AUTH_EMAIL_CHARACTERS:
        return None
    return User.query.filter_by(email=normalised).first()


def _claim_legacy_projects_in_current_transaction(user: User) -> int:
    """Assign ownerless legacy projects only when explicitly allowed.

    This compatibility behavior is useful on an old single-user development DB,
    but it is an ownership risk in production: logging into the only account must
    never silently claim unowned rows. Production config disables it fail-closed.
    """

    if has_app_context() and not current_app.config.get("ALLOW_LEGACY_PROJECT_AUTO_CLAIM", False):
        return 0
    if User.query.count() != 1:
        return 0

    return (
        Project.query.filter(Project.user_id.is_(None))
        .update({Project.user_id: user.id}, synchronize_session=False)
    )


def claim_legacy_projects(user: User) -> int:
    """Safely claim legacy projects after an existing account logs in."""

    try:
        changed = _claim_legacy_projects_in_current_transaction(user)
        if changed:
            db.session.commit()
        return changed
    except SQLAlchemyError:
        db.session.rollback()
        raise


def create_user(data: RegistrationInput) -> User:
    """Create a LifeOS account in one database transaction."""

    if find_user_by_email(data.email):
        raise DuplicateEmailError

    user = User(name=data.name, email=data.email)
    user.set_password(data.password)

    try:
        db.session.add(user)
        db.session.flush()
        _claim_legacy_projects_in_current_transaction(user)
        db.session.commit()
        return user
    except IntegrityError as error:
        db.session.rollback()
        raise DuplicateEmailError from error
    except SQLAlchemyError as error:
        db.session.rollback()
        raise AccountCreationError from error


def authenticate_user(email: str | None, password: str | None) -> User | None:
    """Return the matching user only when the supplied password is valid.

    Authentication inputs are bounded before DB/password work, and an unknown
    account still performs one dummy password verification to reduce basic timing
    enumeration of registered email addresses.
    """

    normalized_email = normalize_email(email)
    supplied_password = str(password or "")
    if (
        not normalized_email
        or len(normalized_email) > MAX_AUTH_EMAIL_CHARACTERS
        or len(supplied_password) > MAX_AUTH_PASSWORD_CHARACTERS
    ):
        check_password_hash(
            _DUMMY_PASSWORD_HASH,
            supplied_password[:MAX_AUTH_PASSWORD_CHARACTERS],
        )
        return None

    user = User.query.filter_by(email=normalized_email).first()
    if user is None:
        check_password_hash(_DUMMY_PASSWORD_HASH, supplied_password)
        return None
    if not user.check_password(supplied_password):
        return None
    return user

"""Authentication business rules for LifeOS.

Routes should remain responsible for HTTP concerns only.  This module owns
registration validation, account creation, legacy-project ownership, and
credential checks so the same behaviour can later be reused by APIs, social
login, and password-recovery workflows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from database import db
from models import Project, User


_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


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

    if not _EMAIL_PATTERN.fullmatch(data.email):
        return "Please enter a valid email address."

    if len(data.password) < 8:
        return "Password must contain at least 8 characters."

    if data.password != data.confirm_password:
        return "The passwords do not match."

    return None


def find_user_by_email(email: str | None) -> User | None:
    """Find an account using the normalised email address."""

    normalised = normalize_email(email)
    if not normalised:
        return None
    return User.query.filter_by(email=normalised).first()


def _claim_legacy_projects_in_current_transaction(user: User) -> int:
    """Assign old ownerless development projects to the only account."""

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
    """Return the matching user only when the supplied password is valid."""

    user = find_user_by_email(email)
    if user is None or not user.check_password(password or ""):
        return None
    return user

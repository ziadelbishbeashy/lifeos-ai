"""Unit tests for the authentication service layer."""

from database import db
from models import Project, User
from services.auth_service import (
    DuplicateEmailError,
    authenticate_user,
    build_registration_input,
    create_user,
    normalize_email,
    validate_registration,
)


def _valid_registration(email="student@example.com"):
    return build_registration_input(
        name="Test Student",
        email=email,
        password="StrongPass123!",
        confirm_password="StrongPass123!",
    )


def test_normalize_email_is_stable():
    assert normalize_email("  Student@Example.COM ") == "student@example.com"


def test_registration_validation_rejects_mismatched_passwords():
    data = build_registration_input(
        name="Test Student",
        email="student@example.com",
        password="StrongPass123!",
        confirm_password="DifferentPass123!",
    )

    assert validate_registration(data) == "The passwords do not match."


def test_create_user_claims_ownerless_legacy_project(app):
    with app.app_context():
        project = Project(title="Legacy Project")
        db.session.add(project)
        db.session.commit()
        project_id = project.id

        account = create_user(_valid_registration())

        claimed_project = db.session.get(Project, project_id)
        assert claimed_project.user_id == account.id


def test_duplicate_email_is_rejected(app):
    with app.app_context():
        create_user(_valid_registration())

        try:
            create_user(_valid_registration("STUDENT@example.com"))
        except DuplicateEmailError:
            pass
        else:
            raise AssertionError("DuplicateEmailError was not raised")


def test_authenticate_user_checks_password(app):
    with app.app_context():
        account = create_user(_valid_registration())

        authenticated = authenticate_user(
            "STUDENT@example.com",
            "StrongPass123!",
        )
        rejected = authenticate_user(
            "student@example.com",
            "wrong-password",
        )

        assert authenticated.id == account.id
        assert rejected is None
        assert User.query.count() == 1


def test_ownerless_legacy_project_is_not_auto_claimed_when_security_flag_is_disabled(app):
    with app.app_context():
        app.config["ALLOW_LEGACY_PROJECT_AUTO_CLAIM"] = False
        project = Project(title="Ownerless production-style project")
        db.session.add(project)
        db.session.commit()
        project_id = project.id

        account = create_user(_valid_registration("secure-owner@example.com"))

        ownerless = db.session.get(Project, project_id)
        assert account.id is not None
        assert ownerless.user_id is None


def test_authentication_rejects_unbounded_credentials(app):
    with app.app_context():
        create_user(_valid_registration())

        assert authenticate_user("x" * 321, "StrongPass123!") is None
        assert authenticate_user("student@example.com", "x" * 257) is None


def test_registration_rejects_unbounded_identity_fields():
    long_name = build_registration_input(
        name="x" * 121,
        email="student@example.com",
        password="StrongPass123!",
        confirm_password="StrongPass123!",
    )
    long_password = build_registration_input(
        name="Test Student",
        email="student@example.com",
        password="x" * 257,
        confirm_password="x" * 257,
    )

    assert "at most 120" in (validate_registration(long_name) or "")
    assert "at most 256" in (validate_registration(long_password) or "")

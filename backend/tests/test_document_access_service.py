"""Legacy document ownership boundary tests."""

import pytest

from database import db
from models import Project, User
from services.document_access_service import (
    DocumentNotFoundError,
    create_legacy_document_metadata,
    require_owned_document,
)


def test_document_is_owned_through_project(app, user):
    with app.app_context():
        project = Project(
            user_id=user,
            title="Owned project",
            status="In Progress",
            priority="Medium",
        )
        db.session.add(project)
        db.session.commit()
        document = create_legacy_document_metadata(
            owner_id=user,
            project_id=project.id,
            filename="brief.pdf",
            storage_key="user-1/brief.pdf",
        )
        assert require_owned_document(document.id, user).id == document.id


def test_document_is_hidden_from_other_user(app, user):
    with app.app_context():
        project = Project(
            user_id=user,
            title="Private project",
            status="In Progress",
            priority="Medium",
        )
        other = User(name="Other", email="other-doc@example.com")
        other.set_password("StrongPass123!")
        db.session.add_all([project, other])
        db.session.commit()
        document = create_legacy_document_metadata(
            owner_id=user,
            project_id=project.id,
            filename="private.pdf",
            storage_key="user-1/private.pdf",
        )
        with pytest.raises(DocumentNotFoundError):
            require_owned_document(document.id, other.id)

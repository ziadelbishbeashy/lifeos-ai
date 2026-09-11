"""Step 14 document-version model/history tests."""

from database import db
from models import (
    Document,
    DocumentVersionFamily,
    Project,
)
from services.document_version_service import (
    get_owned_document_version_history,
)


def test_version_family_orders_history_and_marks_current(app, user):
    with app.app_context():
        project = Project(
            user_id=user,
            title="Versioned project",
        )
        db.session.add(project)
        db.session.flush()

        family = DocumentVersionFamily(
            project_id=project.id,
            user_id=user,
            name="Requirements",
        )
        db.session.add(family)
        db.session.flush()

        version_one = Document(
            project=project,
            version_family=family,
            version_number=1,
            is_current_version=False,
            filename="requirements-v1.pdf",
            file_path="v1.pdf",
            extracted_text="Old requirements",
        )
        version_two = Document(
            project=project,
            version_family=family,
            version_number=2,
            is_current_version=True,
            filename="requirements-v2.pdf",
            file_path="v2.pdf",
            extracted_text="Current requirements",
        )
        db.session.add_all([version_one, version_two])
        db.session.commit()

        history = get_owned_document_version_history(
            document_id=version_one.id,
            owner_id=user,
        )

        assert [item.version_number for item in history.versions] == [1, 2]
        assert history.current_document.id == version_two.id
        assert version_one.is_historical_version is True
        assert version_two.is_historical_version is False
        assert version_two.version_label == "Version 2"


def test_standalone_document_is_treated_as_current_history(app, user):
    with app.app_context():
        project = Project(user_id=user, title="Standalone")
        document = Document(
            project=project,
            filename="notes.pdf",
            file_path="notes.pdf",
        )
        db.session.add_all([project, document])
        db.session.commit()

        history = get_owned_document_version_history(
            document_id=document.id,
            owner_id=user,
        )

        assert history.family is None
        assert history.current_document.id == document.id
        assert history.versions == [document]
        assert document.is_current_version is True

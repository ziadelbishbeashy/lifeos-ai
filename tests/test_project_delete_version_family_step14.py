"""Step 14 project deletion regression with version-family NO ACTION FKs."""

from database import db
from models import Document, DocumentVersionFamily, Project
from services.project_service import delete_project


def test_project_delete_detaches_and_removes_version_family(app, user):
    with app.app_context():
        project = Project(user_id=user, title="Delete versioned")
        db.session.add(project)
        db.session.flush()

        family = DocumentVersionFamily(
            project_id=project.id,
            user_id=user,
            name="Requirements",
        )
        db.session.add(family)
        db.session.flush()

        document = Document(
            project=project,
            version_family=family,
            version_number=1,
            is_current_version=True,
            filename="requirements.pdf",
            file_path="requirements.pdf",
        )
        db.session.add(document)
        db.session.commit()

        project_id = project.id
        family_id = family.id
        document_id = document.id

        delete_project(project)

        assert db.session.get(Project, project_id) is None
        assert db.session.get(DocumentVersionFamily, family_id) is None
        assert db.session.get(Document, document_id) is None

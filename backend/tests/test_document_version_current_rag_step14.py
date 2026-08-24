"""Step 14 current-version filtering for project intelligence."""

from database import db
from models import Document, DocumentVersionFamily, Project
from services.project_question_workflow_service import (
    create_project_document_source_fingerprint,
)
from services.workspace_context_service import build_project_documents_context


def _versioned_project(user):
    project = Project(user_id=user, title="Version-aware project")
    db.session.add(project)
    db.session.flush()

    family = DocumentVersionFamily(
        project_id=project.id,
        user_id=user,
        name="Requirements",
    )
    db.session.add(family)
    db.session.flush()

    old = Document(
        project=project,
        version_family=family,
        version_number=1,
        is_current_version=False,
        filename="requirements-v1.pdf",
        file_path="v1.pdf",
        extracted_text="Deadline is August 20.",
    )
    current = Document(
        project=project,
        version_family=family,
        version_number=2,
        is_current_version=True,
        filename="requirements-v2.pdf",
        file_path="v2.pdf",
        extracted_text="Deadline is August 27.",
    )
    db.session.add_all([old, current])
    db.session.commit()
    return project, old, current


def test_project_fingerprint_ignores_previous_version_changes(app, user):
    with app.app_context():
        project, old, current = _versioned_project(user)

        first = create_project_document_source_fingerprint(
            project_id=project.id,
            user_id=user,
        )

        old.extracted_text = "Historical text edited only for test."
        db.session.commit()

        second = create_project_document_source_fingerprint(
            project_id=project.id,
            user_id=user,
        )

        assert first == second

        current.extracted_text = "Deadline is September 2."
        db.session.commit()

        third = create_project_document_source_fingerprint(
            project_id=project.id,
            user_id=user,
        )

        assert third != second


def test_workspace_context_excludes_previous_versions(app, user):
    with app.app_context():
        project, old, current = _versioned_project(user)

        documents, counts = build_project_documents_context(
            owner_id=user,
            project_id=project.id,
        )

        ids = {item["id"] for item in documents}
        assert current.id in ids
        assert old.id not in ids
        assert counts["total_project_documents"] == 1

"""Step 13A regression test for SQL Server-safe project deletion."""

from database import db
from models import (
    Document,
    DocumentComparison,
    Project,
)
from services.project_service import (
    delete_project,
)


def test_project_delete_removes_comparisons_before_source_documents(app, user):
    with app.app_context():
        first_project = Project(
            user_id=user,
            title="Old project",
        )
        second_project = Project(
            user_id=user,
            title="Current project",
        )

        document_a = Document(
            project=first_project,
            filename="old.pdf",
            file_path="old.pdf",
            extracted_text="Old requirement.",
        )
        document_b = Document(
            project=second_project,
            filename="current.pdf",
            file_path="current.pdf",
            extracted_text="Current requirement.",
        )

        db.session.add_all(
            [
                first_project,
                second_project,
                document_a,
                document_b,
            ]
        )
        db.session.flush()

        comparison = DocumentComparison(
            user_id=user,
            document_a_id=document_a.id,
            document_b_id=document_b.id,
            provider="test",
            model="test-model",
            status="Completed",
            source_fingerprint="c" * 64,
        )
        db.session.add(comparison)
        db.session.commit()

        comparison_id = comparison.id
        first_project_id = first_project.id
        second_document_id = document_b.id

        deleted_title = delete_project(
            first_project
        )

        assert deleted_title == "Old project"
        assert db.session.get(
            Project,
            first_project_id,
        ) is None
        assert db.session.get(
            DocumentComparison,
            comparison_id,
        ) is None

        # The source in the other project is not deleted.
        assert db.session.get(
            Document,
            second_document_id,
        ) is not None

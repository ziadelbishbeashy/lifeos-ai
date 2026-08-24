"""Step 14 replacement workflow, page-change and stale-result tests."""

from types import SimpleNamespace

from database import db
from models import (
    Document,
    DocumentAIAnalysis,
    DocumentQuestion,
    DocumentTaskSuggestion,
    Project,
    ProjectQuestion,
)
from services.document_service import CreatedProjectDocument
from services import document_version_service as service
from storage.local import LocalStorage


def _project_document(user):
    project = Project(
        user_id=user,
        title="LifeOS",
    )
    document = Document(
        project=project,
        filename="requirements-v1.pdf",
        file_path="old.pdf",
        extracted_text=(
            "--- Page 1 ---\nAuthentication is required.\n"
            "--- Page 2 ---\nDeadline is August 20."
        ),
    )
    db.session.add_all([project, document])
    db.session.commit()
    return project, document


def test_page_change_detection_distinguishes_changed_added_removed():
    result = service.detect_document_version_changes(
        old_text=(
            "--- Page 1 ---\nSame\n"
            "--- Page 2 ---\nOld deadline\n"
            "--- Page 3 ---\nRemoved"
        ),
        new_text=(
            "--- Page 1 ---\nSame\n"
            "--- Page 2 ---\nNew deadline\n"
            "--- Page 4 ---\nAdded"
        ),
        from_document_id=1,
        from_version=1,
        to_document_id=2,
        to_version=2,
    )

    assert result["changed_pages"] == [2]
    assert result["added_pages"] == [4]
    assert result["removed_pages"] == [3]
    assert result["unchanged_pages"] == [1]
    assert result["content_changed"] is True


def test_new_version_marks_old_derived_results_outdated(
    app,
    user,
    tmp_path,
    monkeypatch,
):
    with app.app_context():
        project, old_document = _project_document(user)

        analysis = DocumentAIAnalysis(
            document_id=old_document.id,
            user_id=user,
            provider="test",
            model="test-model",
            status="Completed",
            source_fingerprint="a" * 64,
        )
        db.session.add(analysis)
        db.session.flush()

        question = DocumentQuestion(
            document_id=old_document.id,
            user_id=user,
            question="When is release?",
            answer="August 20",
            provider="test",
            model="test-model",
            status="Completed",
            source_fingerprint="b" * 64,
        )
        suggestion = DocumentTaskSuggestion(
            analysis_id=analysis.id,
            document_id=old_document.id,
            user_id=user,
            title="Prepare release",
            status="Pending",
        )
        project_question = ProjectQuestion(
            project_id=project.id,
            user_id=user,
            question="What is the deadline?",
            answer="August 20",
            provider="test",
            model="test-model",
            status="Completed",
            source_fingerprint="c" * 64,
        )
        db.session.add_all([question, suggestion, project_question])
        db.session.commit()

        storage = LocalStorage(tmp_path)
        old_key = storage.save(
            stream=__import__("io").BytesIO(b"old-pdf"),
            original_name="old.pdf",
            namespace="versions",
        )
        old_document.file_path = old_key
        db.session.commit()

        def fake_create_project_pdf_document(*args, **kwargs):
            new_key = storage.save(
                stream=__import__("io").BytesIO(b"new-pdf"),
                original_name="requirements-v2.pdf",
                namespace="versions",
            )
            new_document = Document(
                project_id=project.id,
                filename="requirements-v2.pdf",
                file_path=new_key,
                extracted_text=(
                    "--- Page 1 ---\nAuthentication is required.\n"
                    "--- Page 2 ---\nDeadline is August 27."
                ),
            )
            db.session.add(new_document)
            db.session.commit()

            return CreatedProjectDocument(
                document=new_document,
                original_name="requirements-v2.pdf",
                safe_name="requirements-v2.pdf",
                size_bytes=100,
                storage_key=new_key,
                extraction_succeeded=True,
                page_count=2,
                pages_with_text=2,
                extracted_characters=len(new_document.extracted_text),
                extraction_message=None,
                indexing_succeeded=True,
                chunk_count=2,
                indexing_message=None,
            )

        monkeypatch.setattr(
            service,
            "create_project_pdf_document",
            fake_create_project_pdf_document,
        )
        monkeypatch.setattr(
            service,
            "ensure_owned_document_embeddings",
            lambda **kwargs: SimpleNamespace(
                embedded_count=2,
                reused_count=0,
            ),
        )

        result = service.create_new_document_version(
            upload=None,
            source_document_id=old_document.id,
            owner_id=user,
            max_bytes=1024 * 1024,
            storage=storage,
        )

        db.session.refresh(old_document)
        db.session.refresh(analysis)
        db.session.refresh(question)
        db.session.refresh(suggestion)
        db.session.refresh(project_question)

        assert old_document.version_number == 1
        assert old_document.is_current_version is False
        assert result.current_document.version_number == 2
        assert result.current_document.is_current_version is True
        assert result.current_document.version_family_id == old_document.version_family_id
        assert result.change_summary["changed_pages"] == [2]
        assert analysis.status == "Outdated"
        assert question.status == "Outdated"
        assert suggestion.status == "Outdated"
        assert project_question.status == "Outdated"
        assert result.embeddings_succeeded is True

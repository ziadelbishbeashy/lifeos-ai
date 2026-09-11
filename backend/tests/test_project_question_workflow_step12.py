"""Step 12 project question workflow tests."""

from types import SimpleNamespace

from database import db
from models import Document, Project, ProjectQuestion
import services.project_question_workflow_service as workflow


def _setup_project(user):
    project = Project(user_id=user, title="LifeOS")
    document_a = Document(
        project=project,
        filename="requirements.pdf",
        file_path="requirements.pdf",
        extracted_text="Authentication is required.",
    )
    document_b = Document(
        project=project,
        filename="plan.pdf",
        file_path="plan.pdf",
        extracted_text="Release is due Friday.",
    )
    db.session.add_all([project, document_a, document_b])
    db.session.commit()
    return project, document_a, document_b


def test_project_question_saves_sources_from_multiple_documents(app, user, monkeypatch):
    with app.app_context():
        project, document_a, document_b = _setup_project(user)

        sources = [
            SimpleNamespace(
                document=document_a,
                chunk=SimpleNamespace(id=101, chunk_index=0),
                text="Authentication is required.",
                matched_terms=("authentication",),
                source=lambda: {
                    "document_id": document_a.id,
                    "filename": document_a.filename,
                    "page": 2,
                    "section": "Security",
                    "chunk_id": 101,
                    "chunk_index": 0,
                    "evidence": "Authentication is required.",
                },
            ),
            SimpleNamespace(
                document=document_b,
                chunk=SimpleNamespace(id=201, chunk_index=0),
                text="Release is due Friday.",
                matched_terms=("release",),
                source=lambda: {
                    "document_id": document_b.id,
                    "filename": document_b.filename,
                    "page": 5,
                    "section": "Timeline",
                    "chunk_id": 201,
                    "chunk_index": 0,
                    "evidence": "Release is due Friday.",
                },
            ),
        ]

        fake_result = SimpleNamespace(
            project=project,
            query="What is required and when is release?",
            chunks=sources,
        )

        monkeypatch.setattr(
            workflow,
            "retrieve_owned_project_document_chunks",
            lambda **kwargs: fake_result,
        )
        monkeypatch.setattr(
            workflow,
            "build_project_retrieval_context",
            lambda result, max_characters: (
                '[Source 1 | Document "requirements.pdf" | Page 2 | Security]\nAuthentication is required.\n\n'
                '[Source 2 | Document "plan.pdf" | Page 5 | Timeline]\nRelease is due Friday.'
            ),
        )
        monkeypatch.setattr(
            workflow,
            "verify_document_answerability",
            lambda **kwargs: SimpleNamespace(
                answerable=True,
                source_ids=(1, 2),
                provider="test",
                model="verifier",
            ),
        )
        monkeypatch.setattr(
            workflow,
            "select_project_retrieval_sources",
            lambda retrieval_result, source_ids: retrieval_result,
        )
        monkeypatch.setattr(
            workflow,
            "ask_project_documents_question",
            lambda **kwargs: {
                "provider": "test",
                "model": "answer-model",
                "found_in_document": True,
                "answer": "",
                "claims": [
                    {"text": "Authentication is required.", "source_ids": [1]},
                    {"text": "Release is due Friday.", "source_ids": [2]},
                ],
            },
        )

        saved = workflow.ask_owned_project_documents(
            project_id=project.id,
            user_id=user,
            question_text="What is required and when is release?",
        )

        assert saved.reused_existing is False
        assert saved.question.status == "Completed"
        assert {source["document_id"] for source in saved.question.sources} == {
            document_a.id,
            document_b.id,
        }


def test_project_answer_cache_invalidates_when_any_pdf_changes(app, user):
    with app.app_context():
        project, _, document_b = _setup_project(user)

        first = workflow.create_project_document_source_fingerprint(
            project_id=project.id,
            user_id=user,
        )

        document_b.extracted_text = "Release date changed to Monday."
        db.session.commit()

        second = workflow.create_project_document_source_fingerprint(
            project_id=project.id,
            user_id=user,
        )

        assert first != second

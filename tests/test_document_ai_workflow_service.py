"""Tests for the persistent Document Brain workflow."""

import pytest

from database import db
from models import (
    Document,
    DocumentAIAnalysis,
    Project,
)
from services.ai_service import AIServiceError
from services import document_ai_workflow_service as workflow
from services.document_ai_workflow_service import (
    DocumentAnalysisWorkflowError,
    DocumentNotFoundError,
    DocumentNotReadyError,
    analyse_owned_document,
)


def create_document(
    *,
    user_id: int,
    extracted_text: str | None,
) -> Document:
    project = Project(
        user_id=user_id,
        title="Document Brain Project",
        status="In Progress",
        priority="High",
    )

    document = Document(
        project=project,
        filename="requirements.pdf",
        file_path="stored/requirements.pdf",
        extracted_text=extracted_text,
    )

    db.session.add(project)
    db.session.add(document)
    db.session.commit()

    return document


def fake_ai_result():
    return {
        "success": True,
        "provider": "gemini",
        "model": "test-model",
        "input_characters": 50,
        "analysis": {
            "document_type": (
                "Requirements Document"
            ),
            "title": "LifeOS Requirements",
            "summary": (
                "The document defines the main "
                "LifeOS requirements."
            ),
            "purpose": (
                "Define the project capabilities."
            ),
            "key_points": [],
            "requirements": [
                {
                    "requirement": (
                        "Support document analysis"
                    ),
                    "details": (
                        "PDF documents must be understood."
                    ),
                    "source": {
                        "page": 2,
                        "section": "Document Brain",
                        "evidence": (
                            "Analyse uploaded documents."
                        ),
                    },
                }
            ],
            "decisions": [],
            "risks": [],
            "deadlines": [],
            "action_items": [],
            "missing_information": [],
        },
    }


def test_owned_document_analysis_is_saved(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "LifeOS requirements."
            ),
        )

        monkeypatch.setattr(
            workflow,
            "analyze_document",
            lambda **kwargs: fake_ai_result(),
        )

        result = analyse_owned_document(
            document_id=document.id,
            user_id=user,
        )

        assert result.reused_existing is False
        assert result.analysis.status == "Completed"
        assert result.analysis.provider == "gemini"
        assert result.analysis.model == "test-model"

        assert result.analysis.document_type == (
            "Requirements Document"
        )

        assert result.analysis.insights[
            "requirements"
        ][0]["requirement"] == (
            "Support document analysis"
        )

        saved_document = db.session.get(
            Document,
            document.id,
        )

        assert saved_document.summary.startswith(
            "The document defines"
        )


def test_unchanged_document_reuses_analysis(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "Stable document content."
            ),
        )

        call_count = {"value": 0}

        def fake_analyze(**kwargs):
            call_count["value"] += 1
            return fake_ai_result()

        monkeypatch.setattr(
            workflow,
            "analyze_document",
            fake_analyze,
        )

        first_result = analyse_owned_document(
            document_id=document.id,
            user_id=user,
        )

        second_result = analyse_owned_document(
            document_id=document.id,
            user_id=user,
        )

        assert first_result.reused_existing is False
        assert second_result.reused_existing is True

        assert (
            second_result.analysis.id
            == first_result.analysis.id
        )

        assert call_count["value"] == 1


def test_force_creates_new_analysis(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text=(
                "--- Page 1 ---\n"
                "Stable content."
            ),
        )

        monkeypatch.setattr(
            workflow,
            "analyze_document",
            lambda **kwargs: fake_ai_result(),
        )

        first_result = analyse_owned_document(
            document_id=document.id,
            user_id=user,
        )

        second_result = analyse_owned_document(
            document_id=document.id,
            user_id=user,
            force=True,
        )

        assert first_result.analysis.id != (
            second_result.analysis.id
        )

        assert second_result.reused_existing is False

        analysis_count = (
            DocumentAIAnalysis.query
            .filter_by(
                document_id=document.id
            )
            .count()
        )

        assert analysis_count == 2


def test_document_owned_by_another_user_is_blocked(
    app,
    user,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable content.",
        )

        with pytest.raises(
            DocumentNotFoundError,
            match="not found",
        ):
            analyse_owned_document(
                document_id=document.id,
                user_id=user + 9999,
            )


def test_document_without_text_is_not_ready(
    app,
    user,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="",
        )

        with pytest.raises(
            DocumentNotReadyError,
            match="no readable extracted text",
        ):
            analyse_owned_document(
                document_id=document.id,
                user_id=user,
            )


def test_ai_failure_is_recorded(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable content.",
        )

        def fail_analysis(**kwargs):
            raise AIServiceError(
                "The AI provider is unavailable."
            )

        monkeypatch.setattr(
            workflow,
            "analyze_document",
            fail_analysis,
        )

        monkeypatch.setattr(
            workflow,
            "get_ai_configuration",
            lambda: {
                "provider": "gemini",
                "model": "test-model",
            },
        )

        with pytest.raises(
            DocumentAnalysisWorkflowError,
            match="provider is unavailable",
        ):
            analyse_owned_document(
                document_id=document.id,
                user_id=user,
            )

        failed_analysis = (
            DocumentAIAnalysis.query
            .filter_by(
                document_id=document.id,
                status="Failed",
            )
            .first()
        )

        assert failed_analysis is not None
        assert failed_analysis.provider == "gemini"
        assert failed_analysis.model == "test-model"

        assert (
            "provider is unavailable"
            in failed_analysis.error_message
        )


def test_analysis_fingerprint_includes_schema_version():
    first = workflow._create_source_fingerprint(
        "Stable document text."
    )

    second = workflow._create_source_fingerprint(
        "Stable document text."
    )

    plain_text_hash = __import__("hashlib").sha256(
        b"Stable document text."
    ).hexdigest()

    assert first == second
    assert first != plain_text_hash


def test_suggestion_save_failure_rolls_back_and_is_recorded(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable content.",
        )

        monkeypatch.setattr(
            workflow,
            "analyze_document",
            lambda **kwargs: fake_ai_result(),
        )

        monkeypatch.setattr(
            workflow,
            "build_document_task_suggestions",
            lambda **kwargs: (_ for _ in ()).throw(
                workflow.DocumentSuggestionBuildError(
                    "Suggestion building failed."
                )
            ),
        )

        monkeypatch.setattr(
            workflow,
            "get_ai_configuration",
            lambda: {
                "provider": "gemini",
                "model": "test-model",
            },
        )

        with pytest.raises(
            DocumentAnalysisWorkflowError,
            match="could not save",
        ):
            analyse_owned_document(
                document_id=document.id,
                user_id=user,
            )

        completed_count = (
            DocumentAIAnalysis.query
            .filter_by(
                document_id=document.id,
                status="Completed",
            )
            .count()
        )

        failed_analysis = (
            DocumentAIAnalysis.query
            .filter_by(
                document_id=document.id,
                status="Failed",
            )
            .first()
        )

        assert completed_count == 0
        assert failed_analysis is not None
        assert "Suggestion building failed" in (
            failed_analysis.error_message
        )

"""Tests for ownership-aware document type detection."""

import pytest

from database import db
from models import (
    Document,
    Project,
)
from services import (
    document_type_detection_workflow_service as workflow,
)
from services.document_type_detection_service import (
    DocumentTypeDetectionResult,
)
from services.document_type_detection_workflow_service import (
    DocumentTypeDetectionNotFoundError,
    DocumentTypeDetectionNotReadyError,
    detect_owned_document_type,
)


def create_document(
    *,
    user_id: int,
    extracted_text: str | None,
) -> Document:
    project = Project(
        user_id=user_id,
        title="Type Detection Project",
        status="In Progress",
        priority="Medium",
    )

    document = Document(
        project=project,
        filename="sample.pdf",
        file_path="stored/sample.pdf",
        extracted_text=extracted_text,
    )

    db.session.add(
        project
    )
    db.session.add(
        document
    )
    db.session.commit()

    return document


def fake_detection():
    return DocumentTypeDetectionResult(
        document_type_key="research_paper",
        document_type_label="Research Paper",
        confidence="high",
        reason="Research structure detected.",
        provider="gemini",
        model="test-model",
        sampled_characters=500,
        document_characters=2_000,
    )


def test_owned_document_can_be_detected(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text=(
                "Abstract. Methodology. Results."
            ),
        )

        monkeypatch.setattr(
            workflow,
            "detect_document_type",
            lambda **kwargs: fake_detection(),
        )

        result = detect_owned_document_type(
            document_id=document.id,
            user_id=user,
        )

        assert result.document.id == document.id
        assert (
            result.detection.document_type_key
            == "research_paper"
        )


def test_other_user_cannot_detect_document_type(
    app,
    user,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable content.",
        )

        with pytest.raises(
            DocumentTypeDetectionNotFoundError,
            match="not found",
        ):
            detect_owned_document_type(
                document_id=document.id,
                user_id=user + 999,
            )


def test_document_without_text_is_not_ready(
    app,
    user,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text=None,
        )

        with pytest.raises(
            DocumentTypeDetectionNotReadyError,
            match="no readable",
        ):
            detect_owned_document_type(
                document_id=document.id,
                user_id=user,
            )


def test_unchanged_document_type_detection_is_cached(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Abstract. Methods. Results. Stable content.",
        )
        calls = {"value": 0}

        def detected(**kwargs):
            calls["value"] += 1
            return fake_detection()

        monkeypatch.setattr(workflow, "detect_document_type", detected)

        first = detect_owned_document_type(document_id=document.id, user_id=user)
        second = detect_owned_document_type(document_id=document.id, user_id=user)

        assert first.reused_existing is False
        assert second.reused_existing is True
        assert second.detection.document_type_key == "research_paper"
        assert calls["value"] == 1


def test_changed_document_text_invalidates_type_detection_cache(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Abstract. First version.",
        )
        calls = {"value": 0}

        def detected(**kwargs):
            calls["value"] += 1
            return fake_detection()

        monkeypatch.setattr(workflow, "detect_document_type", detected)
        detect_owned_document_type(document_id=document.id, user_id=user)

        document.extracted_text = "Abstract. Second materially changed version."
        db.session.commit()

        result = detect_owned_document_type(document_id=document.id, user_id=user)
        assert result.reused_existing is False
        assert calls["value"] == 2


def test_duplicate_running_type_detection_is_rejected_before_provider_call(
    app,
    user,
    monkeypatch,
):
    from services.ai_operation_lock_service import AIOperationAlreadyRunningError
    from services.document_type_detection_workflow_service import DocumentTypeDetectionInProgressError

    with app.app_context():
        document = create_document(
            user_id=user,
            extracted_text="Readable content for concurrent classification.",
        )
        provider_calls = {"value": 0}

        def provider(**kwargs):
            provider_calls["value"] += 1
            return fake_detection()

        class BusyLock:
            def __enter__(self):
                raise AIOperationAlreadyRunningError("busy")
            def __exit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr(workflow, "detect_document_type", provider)
        monkeypatch.setattr(workflow, "ai_operation_lock", lambda **kwargs: BusyLock())

        with pytest.raises(DocumentTypeDetectionInProgressError, match="already being checked"):
            detect_owned_document_type(document_id=document.id, user_id=user)

        assert provider_calls["value"] == 0

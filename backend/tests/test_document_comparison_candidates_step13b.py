"""Step 13B comparison candidate-builder tests."""

import hashlib
import json

from database import db
from models import (
    Document,
    DocumentAIAnalysis,
    DocumentChunk,
    Project,
)
from services.document_analysis_service import (
    DOCUMENT_ANALYSIS_SCHEMA_VERSION,
)
from services import document_comparison_candidate_service as service


def _project_documents(user):
    project = Project(
        user_id=user,
        title="Comparison project",
    )

    document_a = Document(
        project=project,
        filename="requirements-v1.pdf",
        file_path="requirements-v1.pdf",
        extracted_text=(
            "--- Page 1 ---\n"
            "Authentication is required.\n"
            "--- Page 2 ---\n"
            "Password length is eight."
        ),
    )

    document_b = Document(
        project=project,
        filename="requirements-v2.pdf",
        file_path="requirements-v2.pdf",
        extracted_text=(
            "--- Page 1 ---\n"
            "Authenticated project membership is required.\n"
            "--- Page 2 ---\n"
            "Password length is twelve."
        ),
    )

    db.session.add_all(
        [
            project,
            document_a,
            document_b,
        ]
    )
    db.session.commit()

    return document_a, document_b


def _modern_fingerprint(text, confirmed_type_key):
    payload = (
        f"{DOCUMENT_ANALYSIS_SCHEMA_VERSION}\n"
        f"{confirmed_type_key}\n"
        f"{text.strip()}"
    )

    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


def _analysis(document, user):
    insights = {
        "document_type": "Requirements / Specification",
        "type_metadata": {
            "confirmed_type_key": "requirements_specification",
        },
        "requirements": [
            {
                "requirement": "Users must authenticate.",
                "details": "Authentication is mandatory.",
                "source": {
                    "page": 1,
                    "section": "Authentication",
                    "evidence": "Authentication is required.",
                },
            },
            {
                "requirement": "Password minimum is eight.",
                "details": "Minimum password length is eight.",
                "source": {
                    "page": 2,
                    "section": "Password policy",
                    "evidence": "Password length is eight.",
                },
            },
        ],
        "key_points": [],
        "decisions": [],
        "risks": [],
        "deadlines": [],
        "action_items": [],
        "type_specific": {},
    }

    analysis = DocumentAIAnalysis(
        document_id=document.id,
        user_id=user,
        provider="test",
        model="test-model",
        status="Completed",
        document_type="Requirements / Specification",
        summary="Requirements",
        insights_json=json.dumps(insights),
        source_fingerprint=_modern_fingerprint(
            document.extracted_text,
            "requirements_specification",
        ),
    )
    db.session.add(analysis)
    db.session.commit()

    return analysis


def test_current_structured_analysis_builds_page_aware_a_sources(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document_a, document_b = _project_documents(user)
        analysis = _analysis(document_a, user)

        monkeypatch.setattr(
            service,
            "_chunk_candidates",
            lambda **kwargs: [],
        )

        bundle = service.build_owned_document_comparison_candidates(
            owner_id=user,
            document_a_id=document_a.id,
            document_b_id=document_b.id,
        )

        assert bundle.coverage_a.analysis_status == "Current"
        assert bundle.coverage_a.analysis_id == analysis.id
        assert bundle.evidence_a[0].source_id == "A1"
        assert bundle.evidence_a[0].kind == "requirement"
        assert bundle.evidence_a[0].page == 1
        assert bundle.evidence_a[0].evidence == "Authentication is required."
        assert bundle.coverage_b.analysis_status == "Not analysed"


def test_stale_structured_analysis_is_not_used_as_current_truth(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document_a, document_b = _project_documents(user)
        _analysis(document_a, user)

        document_a.extracted_text = (
            "--- Page 1 ---\n"
            "The document changed after analysis."
        )
        db.session.commit()

        def fake_chunks(*, document, owner_id, limit):
            if document.id != document_a.id:
                return []

            return [
                {
                    "kind": "chunk",
                    "topic": "Changed",
                    "statement": "The document changed after analysis.",
                    "detail": "",
                    "page": 1,
                    "section": "Changed",
                    "evidence": "The document changed after analysis.",
                    "origin": "document_chunk",
                    "chunk_id": 501,
                    "chunk_index": 0,
                }
            ]

        monkeypatch.setattr(
            service,
            "_chunk_candidates",
            fake_chunks,
        )

        bundle = service.build_owned_document_comparison_candidates(
            owner_id=user,
            document_a_id=document_a.id,
            document_b_id=document_b.id,
        )

        assert bundle.coverage_a.analysis_status == "Stale"
        assert bundle.coverage_a.structured_evidence_count == 0
        assert bundle.evidence_a[0].origin == "document_chunk"
        assert "Users must authenticate" not in (
            bundle.evidence_a[0].comparison_text
        )


def test_source_ids_preserve_a_b_registry_boundaries(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        document_a, document_b = _project_documents(user)

        def fake_chunks(*, document, owner_id, limit):
            return [
                {
                    "kind": "chunk",
                    "topic": f"Doc {document.id}",
                    "statement": f"Evidence from {document.id}",
                    "detail": "",
                    "page": 1,
                    "section": "",
                    "evidence": f"Evidence from {document.id}",
                    "origin": "document_chunk",
                    "chunk_id": document.id * 10,
                    "chunk_index": 0,
                }
            ]

        monkeypatch.setattr(
            service,
            "_chunk_candidates",
            fake_chunks,
        )

        bundle = service.build_owned_document_comparison_candidates(
            owner_id=user,
            document_a_id=document_a.id,
            document_b_id=document_b.id,
        )

        assert [item.source_id for item in bundle.evidence_a] == ["A1"]
        assert [item.source_id for item in bundle.evidence_b] == ["B1"]

        context = service.build_comparison_evidence_context(bundle)

        assert "DOCUMENT A — BASELINE" in context
        assert "DOCUMENT B — COMPARE AGAINST A" in context
        assert "[A1 |" in context
        assert "[B1 |" in context


def test_diverse_chunk_selection_covers_start_middle_and_end():
    chunks = [
        DocumentChunk(
            id=index + 1,
            document_id=1,
            user_id=1,
            chunk_index=index,
            page_start=index + 1,
            page_end=index + 1,
            text=f"chunk {index}",
            character_count=10,
        )
        for index in range(10)
    ]

    selected = service._select_diverse_chunks(
        chunks,
        limit=4,
    )

    assert selected[0].chunk_index == 0
    assert selected[-1].chunk_index == 9
    assert len(selected) == 4

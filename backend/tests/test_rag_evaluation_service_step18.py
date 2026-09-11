"""Integration contracts for the Step 18 gold evaluation runner."""

from __future__ import annotations

import json
from types import SimpleNamespace

from database import db
from models import Document, DocumentQuestion, Project
from services import rag_evaluation_service as evaluation
from services.document_semantic_retrieval_service import DocumentSemanticRetrievalError


def _owned_document(user_id: int, filename: str, text: str) -> Document:
    project = Project(user_id=user_id, title=f"Project for {filename}")
    db.session.add(project)
    db.session.flush()
    document = Document(
        user_id=user_id,
        project_id=project.id,
        filename=filename,
        file_path=f"stored/{filename}",
        extracted_text=text,
        is_current_version=True,
    )
    db.session.add(document)
    db.session.commit()
    return document


def _dataset(tmp_path, *, filename: str, full: bool = False):
    payload = {
        "version": 1,
        "name": "Step18 test",
        "defaults": {"top_k": 5},
        "thresholds": {
            "retrieval_recall": 1.0,
            **({"answerability_accuracy": 1.0, "citation_recall": 1.0} if full else {}),
        },
        "cases": [
            {
                "id": "budget",
                "scope": {"type": "document", "filename": filename},
                "question": "What is the approved budget?",
                "expected": {
                    "answerable": True,
                    "answer_contains": ["EGP 8.4 million"],
                    "sources": [{"filename": filename, "page": 1}],
                },
            }
        ],
    }
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_step18_retrieval_runner_uses_authoritative_document_retrieval(
    app, user, tmp_path, monkeypatch
):
    with app.app_context():
        document = _owned_document(
            user,
            "finance.pdf",
            "--- Page 1 ---\nThe approved budget is EGP 8.4 million.",
        )
        monkeypatch.setattr(
            "services.document_hybrid_retrieval_service.retrieve_owned_document_chunks_semantically",
            lambda **kwargs: (_ for _ in ()).throw(
                DocumentSemanticRetrievalError("offline in test")
            ),
        )

        report = evaluation.run_rag_evaluation(
            dataset_path=_dataset(tmp_path, filename=document.filename),
            user_id=user,
            mode="retrieval",
        )

        assert report["passed"] is True
        assert report["summary"]["retrieval_recall_mean"] == 1.0
        assert report["cases"][0]["retrieval"]["sources"][0]["filename"] == "finance.pdf"


def test_step18_full_mode_grades_answer_and_removes_evaluation_question_history(
    app, user, tmp_path, monkeypatch
):
    with app.app_context():
        document = _owned_document(
            user,
            "finance.pdf",
            "--- Page 1 ---\nThe approved budget is EGP 8.4 million.",
        )
        monkeypatch.setattr(
            "services.document_hybrid_retrieval_service.retrieve_owned_document_chunks_semantically",
            lambda **kwargs: (_ for _ in ()).throw(
                DocumentSemanticRetrievalError("offline in test")
            ),
        )

        def fake_answer(**kwargs):
            row = DocumentQuestion(
                document_id=document.id,
                user_id=user,
                question=kwargs["question_text"],
                answer="The approved budget is EGP 8.4 million. [Source 1]",
                sources_json=json.dumps(
                    [
                        {
                            "source_id": 1,
                            "document_id": document.id,
                            "filename": document.filename,
                            "page": 1,
                            "section": "",
                            "evidence": "The approved budget is EGP 8.4 million.",
                            "content_type": "text",
                        }
                    ]
                ),
                provider="test",
                model="test-model",
                status="Completed",
                source_fingerprint="x" * 64,
            )
            db.session.add(row)
            db.session.commit()
            return SimpleNamespace(question=row)

        monkeypatch.setattr(evaluation, "ask_owned_document", fake_answer)

        report = evaluation.run_rag_evaluation(
            dataset_path=_dataset(tmp_path, filename=document.filename, full=True),
            user_id=user,
            mode="full",
        )

        assert report["passed"] is True
        assert report["summary"]["answerability_accuracy"] == 1.0
        assert report["summary"]["citation_recall_mean"] == 1.0
        assert DocumentQuestion.query.filter_by(document_id=document.id).count() == 0

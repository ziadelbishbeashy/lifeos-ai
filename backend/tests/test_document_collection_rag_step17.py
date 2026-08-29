"""Regression coverage for Step 17 collection RAG and Step 16 table chunks."""

from __future__ import annotations

import json
from types import SimpleNamespace

from database import db
from models import (
    Document,
    DocumentCollection,
    DocumentCollectionItem,
    DocumentTable,
    DocumentVersionFamily,
    Project,
)
import services.document_collection_question_workflow_service as workflow
import services.document_collection_retrieval_service as retrieval
from services.document_collection_question_workflow_service import (
    create_collection_source_fingerprint,
)
from services.document_collection_retrieval_service import (
    build_collection_context,
    retrieve_owned_collection_chunks,
)
from services.document_embedding_service import DocumentEmbeddingError


def _project(user_id: int, title: str) -> Project:
    row = Project(
        user_id=user_id,
        title=title,
        status="In Progress",
        priority="High",
    )
    db.session.add(row)
    db.session.flush()
    return row


def _document(user_id: int, title: str, filename: str, text: str) -> Document:
    project = _project(user_id, title)
    row = Document(
        project=project,
        filename=filename,
        file_path=f"stored/{filename}",
        extracted_text=text,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _collection(user_id: int, name: str, documents: list[Document]) -> DocumentCollection:
    row = DocumentCollection(user_id=user_id, name=name)
    db.session.add(row)
    db.session.flush()
    db.session.add_all(
        [
            DocumentCollectionItem(collection_id=row.id, document_id=document.id)
            for document in documents
        ]
    )
    db.session.commit()
    return row


def _force_keyword_fallback(monkeypatch):
    def fail_embeddings(**kwargs):
        raise DocumentEmbeddingError("Embedding provider unavailable in test.")

    monkeypatch.setattr(
        retrieval,
        "ensure_owned_document_embeddings",
        fail_embeddings,
    )


def _source_ids_for_text(context: str, needles: list[str]) -> tuple[int, ...]:
    blocks = context.split("\n\n")
    found = []
    for block in blocks:
        header = block.splitlines()[0]
        source_id = int(header.split("Source ", 1)[1].split(" ", 1)[0])
        if any(needle in block for needle in needles):
            found.append(source_id)
    return tuple(found)


def test_collection_source_fingerprint_is_stable_and_table_sensitive(app, user):
    with app.app_context():
        document = _document(
            user,
            "Retail",
            "retail.pdf",
            "--- Page 1 ---\nRetail performance.",
        )
        collection = _collection(user, "Northstar", [document])
        first = create_collection_source_fingerprint(
            collection_id=collection.id,
            user_id=user,
        )
        second = create_collection_source_fingerprint(
            collection_id=collection.id,
            user_id=user,
        )
        assert first == second

        table = DocumentTable(
            document_id=document.id,
            user_id=user,
            page_number=1,
            table_index=1,
            title="Q4 Sales",
            headers_json=json.dumps(["Product", "Q4 units"]),
            rows_json=json.dumps([["Laptop", "3,250"]]),
            markdown_text="| Product | Q4 units |\n| --- | --- |\n| Laptop | 3,250 |",
            row_count=1,
            column_count=2,
            source_fingerprint="a" * 64,
        )
        db.session.add(table)
        db.session.commit()

        changed = create_collection_source_fingerprint(
            collection_id=collection.id,
            user_id=user,
        )
        assert changed != first


def test_collection_keyword_fallback_searches_one_and_multiple_documents(app, user, monkeypatch):
    with app.app_context():
        operations = _document(
            user,
            "Operations",
            "operations.pdf",
            "--- Page 1 ---\nProject codename AURORA-26. Program manager Nadia Fawzy. Public launch 16 November 2026.",
        )
        finance = _document(
            user,
            "Finance",
            "finance.pdf",
            "--- Page 1 ---\nApproved budget EGP 8.4 million. NPS 71. Orbit Rewards loyalty program.",
        )
        retail = _document(
            user,
            "Retail",
            "retail.pdf",
            "--- Page 1 ---\nSmartphones Q4 units 6,700. Cairo annual revenue EGP 38.7 million.",
        )
        single = _collection(user, "One", [operations])
        multi = _collection(user, "Northstar", [operations, finance, retail])
        _force_keyword_fallback(monkeypatch)

        one_result = retrieve_owned_collection_chunks(
            collection_id=single.id,
            user_id=user,
            query="What is the project codename?",
        )
        assert {item.document.id for item in one_result.chunks} == {operations.id}
        assert one_result.mode == "keyword_fallback"

        multi_result = retrieve_owned_collection_chunks(
            collection_id=multi.id,
            user_id=user,
            query="project codename manager approved budget Smartphones Q4 units",
        )
        document_ids = {item.document.id for item in multi_result.chunks}
        assert operations.id in document_ids
        assert finance.id in document_ids
        assert retail.id in document_ids


def test_collection_retrieval_keeps_table_chunks_in_authoritative_rag(app, user, monkeypatch):
    with app.app_context():
        retail = _document(
            user,
            "Retail",
            "retail.pdf",
            "--- Page 1 ---\nQuarterly product performance.",
        )
        table = DocumentTable(
            document_id=retail.id,
            user_id=user,
            page_number=1,
            table_index=1,
            title="Product Performance",
            headers_json=json.dumps(["Product", "Q4 units", "Return rate", "Reorder status"]),
            rows_json=json.dumps(
                [
                    ["Laptop", "3,250", "3.1%", "Below reorder point"],
                    ["Headphones", "2,900", "6.4%", "Above reorder point"],
                    ["Smartwatches", "2,100", "2.7%", "Below reorder point"],
                ]
            ),
            markdown_text=(
                "Table: Product Performance\n"
                "| Product | Q4 units | Return rate | Reorder status |\n"
                "| --- | --- | --- | --- |\n"
                "| Laptop | 3,250 | 3.1% | Below reorder point |\n"
                "| Headphones | 2,900 | 6.4% | Above reorder point |\n"
                "| Smartwatches | 2,100 | 2.7% | Below reorder point |"
            ),
            row_count=3,
            column_count=4,
            source_fingerprint="b" * 64,
        )
        db.session.add(table)
        db.session.commit()
        collection = _collection(user, "Retail tables", [retail])
        _force_keyword_fallback(monkeypatch)

        laptop_result = retrieve_owned_collection_chunks(
            collection_id=collection.id,
            user_id=user,
            query="What were Laptop Q4 unit sales?",
        )
        laptop_context = build_collection_context(laptop_result)
        assert any(item.chunk.content_type == "table" for item in laptop_result.chunks)
        assert "Laptop" in laptop_context
        assert "3,250" in laptop_context

        return_rate_result = retrieve_owned_collection_chunks(
            collection_id=collection.id,
            user_id=user,
            query="What product had the highest return rate?",
        )
        return_rate_context = build_collection_context(return_rate_result)
        assert "Headphones" in return_rate_context
        assert "6.4%" in return_rate_context

        reorder_result = retrieve_owned_collection_chunks(
            collection_id=collection.id,
            user_id=user,
            query="Which categories are below their reorder points?",
        )
        reorder_context = build_collection_context(reorder_result)
        assert "Laptop" in reorder_context
        assert "Smartwatches" in reorder_context
        assert "Below reorder point" in reorder_context


def test_collection_retrieval_excludes_historical_versions(app, user, monkeypatch):
    with app.app_context():
        project = _project(user, "Versioned")
        family = DocumentVersionFamily(project=project, user_id=user, name="Plan")
        db.session.add(family)
        db.session.flush()
        old = Document(
            project=project,
            version_family=family,
            version_number=1,
            is_current_version=False,
            filename="plan-v1.pdf",
            file_path="stored/plan-v1.pdf",
            extracted_text="--- Page 1 ---\nOLD-CODE should not be retrieved.",
        )
        current = Document(
            project=project,
            version_family=family,
            version_number=2,
            is_current_version=True,
            filename="plan-v2.pdf",
            file_path="stored/plan-v2.pdf",
            extracted_text="--- Page 1 ---\nCURRENT-CODE is the active value.",
        )
        db.session.add_all([old, current])
        db.session.flush()
        collection = _collection(user, "Versions", [old, current])
        _force_keyword_fallback(monkeypatch)

        result = retrieve_owned_collection_chunks(
            collection_id=collection.id,
            user_id=user,
            query="OLD-CODE CURRENT-CODE active value",
        )
        assert result.document_count == 1
        assert {item.document.id for item in result.chunks} == {current.id}
        assert "OLD-CODE" not in build_collection_context(result)


def test_collection_question_across_two_documents_saves_both_sources(app, user, monkeypatch):
    with app.app_context():
        operations = _document(
            user,
            "Operations",
            "operations.pdf",
            "--- Page 1 ---\nProject codename AURORA-26. Program manager Nadia Fawzy.",
        )
        finance = _document(
            user,
            "Finance",
            "finance.pdf",
            "--- Page 1 ---\nApproved budget EGP 8.4 million.",
        )
        collection = _collection(user, "Northstar", [operations, finance])
        _force_keyword_fallback(monkeypatch)

        def verify(**kwargs):
            ids = _source_ids_for_text(kwargs["retrieved_context"], ["AURORA-26", "8.4 million"])
            return SimpleNamespace(
                answerable=True,
                source_ids=ids,
                provider="gemini",
                model="test-verifier",
            )

        monkeypatch.setattr(workflow, "verify_document_answerability", verify)
        monkeypatch.setattr(
            workflow,
            "ask_document_collection_question",
            lambda **kwargs: {
                "success": True,
                "provider": "gemini",
                "model": "test-answer",
                "answer": "",
                "found_in_document": True,
                "claims": [
                    {"text": "The project codename is AURORA-26 and it is managed by Nadia Fawzy.", "source_ids": [1]},
                    {"text": "The approved budget is EGP 8.4 million.", "source_ids": [2]},
                ],
            },
        )

        saved = workflow.ask_owned_collection_documents(
            collection_id=collection.id,
            user_id=user,
            question_text="What is the project codename, who manages it, and what is its approved budget?",
        )
        assert "AURORA-26" in saved.question.answer
        assert "EGP 8.4 million" in saved.question.answer
        assert {source["filename"] for source in saved.question.sources} == {
            "operations.pdf",
            "finance.pdf",
        }


def test_collection_question_across_three_documents_and_grounding_guard(app, user, monkeypatch):
    with app.app_context():
        operations = _document(
            user,
            "Operations",
            "operations.pdf",
            "--- Page 1 ---\nPublic launch 16 November 2026.",
        )
        finance = _document(
            user,
            "Finance",
            "finance.pdf",
            "--- Page 1 ---\nApproved budget EGP 8.4 million.",
        )
        retail = _document(
            user,
            "Retail",
            "retail.pdf",
            "--- Page 1 ---\nSmartphones had the highest Q4 unit sales at 6,700 units.",
        )
        collection = _collection(user, "Northstar", [operations, finance, retail])
        _force_keyword_fallback(monkeypatch)

        monkeypatch.setattr(
            workflow,
            "verify_document_answerability",
            lambda **kwargs: SimpleNamespace(
                answerable=True,
                source_ids=_source_ids_for_text(
                    kwargs["retrieved_context"],
                    ["16 November 2026", "8.4 million", "6,700 units"],
                ),
                provider="gemini",
                model="test-verifier",
            ),
        )
        monkeypatch.setattr(
            workflow,
            "ask_document_collection_question",
            lambda **kwargs: {
                "success": True,
                "provider": "gemini",
                "model": "test-answer",
                "answer": "",
                "found_in_document": True,
                "claims": [
                    {"text": "The public launch is 16 November 2026.", "source_ids": [1]},
                    {"text": "The approved budget is EGP 8.4 million.", "source_ids": [2]},
                    {"text": "Smartphones had the highest Q4 unit sales with 6,700 units.", "source_ids": [3]},
                ],
            },
        )
        saved = workflow.ask_owned_collection_documents(
            collection_id=collection.id,
            user_id=user,
            question_text="Give me the program launch date, approved budget, and the product with the highest Q4 unit sales.",
        )
        assert len(saved.question.sources) == 3

        unrelated_retrieval = retrieve_owned_collection_chunks(
            collection_id=collection.id,
            user_id=user,
            query="approved budget launch",
        )
        monkeypatch.setattr(
            workflow,
            "retrieve_owned_collection_chunks",
            lambda **kwargs: unrelated_retrieval,
        )
        monkeypatch.setattr(
            workflow,
            "verify_document_answerability",
            lambda **kwargs: SimpleNamespace(
                answerable=False,
                source_ids=(),
                provider="gemini",
                model="test-verifier",
            ),
        )
        monkeypatch.setattr(
            workflow,
            "ask_document_collection_question",
            lambda **kwargs: (_ for _ in ()).throw(
                AssertionError("Answer AI must not run for unsupported questions.")
            ),
        )
        unsupported = workflow.ask_owned_collection_documents(
            collection_id=collection.id,
            user_id=user,
            question_text="What is the CEO's salary?",
            force=True,
        )
        assert unsupported.question.answer == workflow.NO_MATCH_ANSWER
        assert unsupported.question.sources == []

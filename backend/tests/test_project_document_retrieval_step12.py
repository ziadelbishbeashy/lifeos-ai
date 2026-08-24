"""Step 12 project-wide retrieval tests."""

from types import SimpleNamespace

import pytest

from database import db
from models import Document, DocumentChunk, Project, User
import services.project_document_retrieval_service as service


def _chunk(document_id, chunk_index, text, page):
    return DocumentChunk(
        id=(document_id * 100) + chunk_index + 1,
        document_id=document_id,
        user_id=1,
        chunk_index=chunk_index,
        page_start=page,
        page_end=page,
        section_title="Section",
        text=text,
        character_count=len(text),
        source_fingerprint="a" * 64,
    )


def test_context_preserves_document_filename_page_and_numbering():
    project = Project(id=4, user_id=1, title="LifeOS")
    document_a = Document(id=10, project_id=4, filename="requirements.pdf", file_path="a.pdf")
    document_b = Document(id=11, project_id=4, filename="plan.pdf", file_path="b.pdf")

    hybrid_a = SimpleNamespace(
        chunk=_chunk(10, 0, "Authentication is required.", 2),
        score=0.02,
        keyword_score=3.0,
        semantic_score=0.9,
        keyword_rank=1,
        semantic_rank=1,
        matched_terms=("authentication",),
        page_start=2,
        page_end=2,
        section_title="Security",
        text="Authentication is required.",
        source=lambda: {"page": 2, "section": "Security", "evidence": "Authentication is required."},
    )
    hybrid_b = SimpleNamespace(
        chunk=_chunk(11, 0, "Release is due Friday.", 5),
        score=0.01,
        keyword_score=2.0,
        semantic_score=0.8,
        keyword_rank=2,
        semantic_rank=2,
        matched_terms=("release",),
        page_start=5,
        page_end=5,
        section_title="Timeline",
        text="Release is due Friday.",
        source=lambda: {"page": 5, "section": "Timeline", "evidence": "Release is due Friday."},
    )

    result = service.ProjectDocumentRetrievalResult(
        project=project,
        query="What is required and when is release?",
        chunks=[
            service.ProjectRetrievedDocumentChunk(document=document_a, retrieved=hybrid_a),
            service.ProjectRetrievedDocumentChunk(document=document_b, retrieved=hybrid_b),
        ],
        project_document_count=2,
        searchable_document_count=2,
        skipped_document_count=0,
        mode="hybrid",
        semantic_error=None,
        index_rebuilt_count=0,
        chunks_rebuilt_count=0,
        embedded_count=0,
        reused_count=2,
    )

    context = service.build_project_retrieval_context(result)

    assert '[Source 1 | Document "requirements.pdf" | Page 2 | Security]' in context
    assert '[Source 2 | Document "plan.pdf" | Page 5 | Timeline]' in context


def test_foreign_project_is_rejected(app, user):
    with app.app_context():
        other = User(name="Other", email="step12-other@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.flush()

        project = Project(user_id=other.id, title="Private")
        db.session.add(project)
        db.session.commit()

        with pytest.raises(service.ProjectDocumentRetrievalNotFoundError):
            service.retrieve_owned_project_document_chunks(
                project_id=project.id,
                user_id=user,
                query="What is in the documents?",
            )


def test_verified_source_selection_preserves_cross_document_order():
    project = Project(id=4, user_id=1, title="LifeOS")
    documents = [
        Document(id=10, project_id=4, filename="a.pdf", file_path="a"),
        Document(id=11, project_id=4, filename="b.pdf", file_path="b"),
        Document(id=12, project_id=4, filename="c.pdf", file_path="c"),
    ]

    chunks = []
    for index, document in enumerate(documents, start=1):
        fake = SimpleNamespace(
            chunk=_chunk(document.id, 0, f"Text {index}", index),
            score=0.01,
            keyword_score=1.0,
            semantic_score=0.8,
            keyword_rank=index,
            semantic_rank=index,
            matched_terms=(),
            page_start=index,
            page_end=index,
            section_title=None,
            text=f"Text {index}",
            source=lambda i=index: {"page": i, "section": None, "evidence": f"Text {i}"},
        )
        chunks.append(service.ProjectRetrievedDocumentChunk(document=document, retrieved=fake))

    result = service.ProjectDocumentRetrievalResult(
        project=project,
        query="q",
        chunks=chunks,
        project_document_count=3,
        searchable_document_count=3,
        skipped_document_count=0,
        mode="hybrid",
        semantic_error=None,
        index_rebuilt_count=0,
        chunks_rebuilt_count=0,
        embedded_count=0,
        reused_count=3,
    )

    selected = service.select_project_retrieval_sources(
        retrieval_result=result,
        source_ids=[3, 1],
    )

    assert [item.document.id for item in selected.chunks] == [12, 10]


def test_project_retrieval_uses_one_global_corpus_and_one_question_embedding(
    app,
    user,
    monkeypatch,
):
    with app.app_context():
        project = Project(
            user_id=user,
            title="Multi-document project",
        )
        db.session.add(project)
        db.session.flush()

        first_document = Document(
            project_id=project.id,
            filename="requirements.pdf",
            file_path="requirements.pdf",
            extracted_text="Authentication is required.",
        )
        second_document = Document(
            project_id=project.id,
            filename="timeline.pdf",
            file_path="timeline.pdf",
            extracted_text="Release is due Friday.",
        )
        db.session.add_all([first_document, second_document])
        db.session.flush()

        first_chunk = _chunk(
            first_document.id,
            0,
            "Authentication is required.",
            2,
        )
        first_chunk.user_id = user
        second_chunk = _chunk(
            second_document.id,
            0,
            "Release is due Friday.",
            5,
        )
        second_chunk.user_id = user

        chunks_by_document = {
            first_document.id: [first_chunk],
            second_document.id: [second_chunk],
        }
        documents_by_id = {
            first_document.id: first_document,
            second_document.id: second_document,
        }

        monkeypatch.setattr(
            service,
            "ensure_owned_document_chunks",
            lambda *, document_id, user_id: SimpleNamespace(
                document=documents_by_id[document_id],
                chunks=chunks_by_document[document_id],
                rebuilt=False,
            ),
        )
        monkeypatch.setattr(
            service,
            "ensure_owned_document_embeddings",
            lambda *, document_id, user_id, force=False: SimpleNamespace(
                document=documents_by_id[document_id],
                chunks=chunks_by_document[document_id],
                embedded_count=0,
                reused_count=1,
                chunks_rebuilt=False,
                provider="gemini",
                model="test-embedding",
                dimensions=3,
            ),
        )

        calls = {
            "question_embeddings": 0,
            "keyword_corpus": [],
            "semantic_corpus": [],
        }

        def fake_question_embedding(*, question):
            calls["question_embeddings"] += 1
            return (
                [1.0, 0.0, 0.0],
                SimpleNamespace(
                    provider="gemini",
                    model="test-embedding",
                    dimensions=3,
                ),
            )

        monkeypatch.setattr(
            service,
            "generate_question_embedding",
            fake_question_embedding,
        )

        def fake_keyword_rank(*, query, chunks, limit):
            calls["keyword_corpus"] = list(chunks)
            return []

        monkeypatch.setattr(
            service,
            "rank_document_chunks",
            fake_keyword_rank,
        )

        def fake_semantic_rank(*, question_embedding, chunks, limit):
            calls["semantic_corpus"] = list(chunks)
            return []

        monkeypatch.setattr(
            service,
            "rank_semantic_document_chunks",
            fake_semantic_rank,
        )

        def fake_fuse(*, keyword_chunks, semantic_chunks, limit):
            return [
                SimpleNamespace(
                    chunk=first_chunk,
                    score=0.02,
                    keyword_score=1.0,
                    semantic_score=0.9,
                    keyword_rank=1,
                    semantic_rank=1,
                    matched_terms=("authentication",),
                    page_start=2,
                    page_end=2,
                    section_title="Security",
                    text=first_chunk.text,
                    source=lambda: {
                        "page": 2,
                        "section": "Security",
                        "evidence": first_chunk.text,
                    },
                ),
                SimpleNamespace(
                    chunk=second_chunk,
                    score=0.01,
                    keyword_score=0.8,
                    semantic_score=0.85,
                    keyword_rank=2,
                    semantic_rank=2,
                    matched_terms=("release",),
                    page_start=5,
                    page_end=5,
                    section_title="Timeline",
                    text=second_chunk.text,
                    source=lambda: {
                        "page": 5,
                        "section": "Timeline",
                        "evidence": second_chunk.text,
                    },
                ),
            ][:limit]

        monkeypatch.setattr(service, "fuse_retrieval_results", fake_fuse)

        result = service.retrieve_owned_project_document_chunks(
            project_id=project.id,
            user_id=user,
            query="What is required and when is release?",
        )

        assert calls["question_embeddings"] == 1
        assert {chunk.document_id for chunk in calls["keyword_corpus"]} == {
            first_document.id,
            second_document.id,
        }
        assert {chunk.document_id for chunk in calls["semantic_corpus"]} == {
            first_document.id,
            second_document.id,
        }
        assert result.project_document_count == 2
        assert result.searchable_document_count == 2
        assert {item.document.id for item in result.chunks} == {
            first_document.id,
            second_document.id,
        }


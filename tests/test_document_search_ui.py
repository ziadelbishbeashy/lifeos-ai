"""UI tests aligned with the redesigned Step 8C PDF workspace."""

from types import SimpleNamespace

from database import db
from models import (
    Document,
    Project,
)


def login(client):
    return client.post(
        "/login",
        data={
            "email": "student@example.com",
            "password": "StrongPass123!",
        },
        follow_redirects=True,
    )


def create_document(*, user_id: int) -> int:
    project = Project(
        user_id=user_id,
        title="Search Project",
        status="In Progress",
        priority="Medium",
    )

    document = Document(
        project=project,
        filename="Architecture.pdf",
        file_path="stored/architecture.pdf",
        extracted_text=(
            "--- Page 1 ---\nArchitecture overview.\n"
            "--- Page 8 ---\nPrivate by default protects user data."
        ),
    )

    db.session.add_all(
        [project, document]
    )
    db.session.commit()

    return document.id


def test_document_details_contains_pdf_semantic_workspace(
    app,
    client,
    user,
):
    with app.app_context():
        document_id = create_document(
            user_id=user
        )

    login(client)

    response = client.get(
        f"/documents/{document_id}"
    )

    assert response.status_code == 200

    page = response.get_data(
        as_text=True
    )

    assert 'data-db-tab="search"' in page
    assert 'data-db-panel="search"' in page

    # Step 8C deliberately replaced the old developer-style result list
    # with a full PDF workspace.
    assert "Read and explore the original PDF" in page
    assert "Open PDF" in page
    assert "Semantic search" in page
    assert "In-page highlights" in page
    assert "data-db-open-pdf" in page
    assert "data-db-pdf-semantic-search-url" in page

    # Retrieval diagnostics stay out of the reader-facing workspace.
    assert "Semantic similarity" not in page
    assert "Keyword rank" not in page
    assert "Chunk ID" not in page


def test_legacy_search_route_keeps_results_backend_only(
    app,
    client,
    user,
    monkeypatch,
):
    from routes import document_routes

    with app.app_context():
        document_id = create_document(
            user_id=user
        )

    captured = {}

    def fake_search(**kwargs):
        captured.update(kwargs)

        document = db.session.get(
            Document,
            kwargs["document_id"],
        )

        hit = SimpleNamespace(
            rank=1,
            chunk_id=9,
            chunk_index=3,
            page_start=8,
            page_end=8,
            page_label="8",
            section="Privacy",
            preview=(
                "Private by default protects user data unless "
                "the user explicitly shares it."
            ),
            exact_phrase=True,
            methods=("exact", "keyword", "semantic"),
            method_label="Exact + retrieval",
            match_strength="Exact",
            keyword_score=3.2,
            semantic_score=0.79,
            keyword_rank=1,
            semantic_rank=1,
            matched_terms=("private", "default"),
        )

        return SimpleNamespace(
            document=document,
            query=kwargs["query"],
            hits=(hit,),
            result_count=1,
            mode="hybrid",
            exact_result_count=1,
            keyword_result_count=4,
            semantic_result_count=5,
            semantic_fallback=False,
            semantic_error=None,
            chunks_rebuilt=False,
            embeddings_created=0,
            embeddings_reused=57,
        )

    monkeypatch.setattr(
        document_routes,
        "search_owned_document",
        fake_search,
    )

    login(client)

    response = client.get(
        f"/documents/{document_id}/search?q=private+by+default"
    )

    assert response.status_code == 200
    assert captured["document_id"] == document_id
    assert captured["user_id"] == user
    assert captured["query"] == "private by default"

    page = response.get_data(
        as_text=True
    )

    # The legacy route can still execute the backend retrieval path for
    # compatibility, but Step 8C no longer renders chunk/result diagnostics.
    assert "Read and explore the original PDF" in page
    assert "Open PDF" in page

    assert "Semantic similarity" not in page
    assert "Keyword rank" not in page
    assert "Exact + retrieval" not in page


def test_legacy_search_route_does_not_call_answer_generation(
    app,
    client,
    user,
    monkeypatch,
):
    from routes import document_routes

    with app.app_context():
        document_id = create_document(
            user_id=user
        )

    def fake_search(**kwargs):
        document = db.session.get(
            Document,
            kwargs["document_id"],
        )

        return SimpleNamespace(
            document=document,
            query=kwargs["query"],
            hits=(),
            result_count=0,
            mode="hybrid",
            exact_result_count=0,
            keyword_result_count=0,
            semantic_result_count=2,
            semantic_fallback=False,
            semantic_error=None,
            chunks_rebuilt=False,
            embeddings_created=0,
            embeddings_reused=10,
        )

    monkeypatch.setattr(
        document_routes,
        "search_owned_document",
        fake_search,
    )

    monkeypatch.setattr(
        document_routes,
        "ask_owned_document",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "Ask Document must not run during direct search."
            )
        ),
    )

    login(client)

    response = client.get(
        f"/documents/{document_id}/search?q=unrelated+concept"
    )

    assert response.status_code == 200

    page = response.get_data(
        as_text=True
    )

    # Step 8C uses the PDF reader for user-facing search results.
    assert "Read and explore the original PDF" in page
    assert "Open PDF" in page
    assert "No passages matched this search" not in page

"""Tests for the reader-safe Step 8C semantic PDF search payload."""

from types import SimpleNamespace

import services.document_pdf_search_service as service


def test_pdf_search_hides_retrieval_internals(monkeypatch):
    hit = SimpleNamespace(
        page_start=8,
        page_end=8,
        page_label="8",
        section="Privacy",
        preview="Ownership is checked before private data is returned.",
        match_strength="Strong",
        chunk_id=57,
        chunk_index=12,
        semantic_score=0.8123,
        semantic_rank=1,
        keyword_rank=2,
        matched_terms=("ownership", "private"),
    )

    monkeypatch.setattr(
        service,
        "search_owned_document",
        lambda **kwargs: SimpleNamespace(
            document=SimpleNamespace(id=4),
            query="how is data protected",
            hits=(hit,),
            result_count=1,
            semantic_fallback=False,
        ),
    )

    result = service.search_owned_document_for_pdf(
        document_id=4,
        user_id=9,
        query="how is data protected",
    )

    payload = result.as_dict()
    match = payload["matches"][0]

    assert match == {
        "match_id": "match-1",
        "page_start": 8,
        "page_end": 8,
        "page_label": "8",
        "section": "Privacy",
        "text": "Ownership is checked before private data is returned.",
        "emphasis": "strong",
    }

    serialized = str(payload)
    assert "chunk_id" not in serialized
    assert "chunk_index" not in serialized
    assert "semantic_score" not in serialized
    assert "semantic_rank" not in serialized
    assert "keyword_rank" not in serialized
    assert "matched_terms" not in serialized


def test_related_match_uses_lighter_emphasis(monkeypatch):
    hit = SimpleNamespace(
        page_start=3,
        page_end=4,
        page_label="3-4",
        section="Background",
        preview="A related background passage.",
        match_strength="Related",
    )

    monkeypatch.setattr(
        service,
        "search_owned_document",
        lambda **kwargs: SimpleNamespace(
            document=SimpleNamespace(id=1),
            query="background concept",
            hits=(hit,),
            result_count=1,
            semantic_fallback=False,
        ),
    )

    result = service.search_owned_document_for_pdf(
        document_id=1,
        user_id=2,
        query="background concept",
    )

    assert result.matches[0].emphasis == "related"
    assert result.matches[0].page_start == 3
    assert result.matches[0].page_end == 4

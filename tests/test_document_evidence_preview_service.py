"""Tests for deterministic focused evidence previews."""

from services.document_evidence_preview_service import (
    MAX_EVIDENCE_PREVIEW_CHARACTERS,
    build_focused_evidence_preview,
)


def test_relevant_sentence_is_selected_from_middle():
    source = (
        "This section gives a general introduction to the platform. "
        "It also describes the visual design at a high level. "
        "Every project query is filtered by the current user "
        "identifier before data is returned. "
        "The final section lists future interface improvements."
    )

    preview = build_focused_evidence_preview(
        source,
        question=(
            "How does LifeOS separate project data "
            "between users?"
        ),
        claim_text=(
            "Project queries are filtered by the "
            "current user identifier."
        ),
        matched_terms=(
            "project",
            "user",
        ),
        max_characters=220,
    )

    assert preview.focused is True
    assert (
        "Every project query is filtered by the "
        "current user identifier"
        in preview.text
    )
    assert (
        "visual design"
        not in preview.text
    )


def test_page_markers_are_removed():
    preview = build_focused_evidence_preview(
        (
            "--- Page 8 ---\n"
            "Private information remains private unless "
            "the student explicitly shares it."
        ),
        question="What remains private?",
        claim_text="Private information remains private.",
    )

    assert "--- Page" not in preview.text
    assert "Private information" in preview.text


def test_preview_is_bounded_and_word_safe():
    source = (
        "Introduction sentence. "
        + "unrelated " * 100
        + "Object-level ownership checks protect each account. "
        + "additional " * 100
    )

    preview = build_focused_evidence_preview(
        source,
        question="How is each account protected?",
        claim_text=(
            "Object-level ownership checks protect "
            "each account."
        ),
        max_characters=180,
    )

    assert len(preview.text) <= 180
    assert "ownership checks" in preview.text
    assert not preview.text.endswith(
        "additiona"
    )


def test_no_term_match_uses_safe_leading_preview():
    source = (
        "The first document sentence explains the project. "
        "The second sentence adds implementation details."
    )

    preview = build_focused_evidence_preview(
        source,
        question="What recipe should I cook?",
        claim_text="",
        matched_terms=(),
        max_characters=160,
    )

    assert preview.focused is False
    assert preview.text.startswith(
        "The first document sentence"
    )


def test_matched_retrieval_terms_receive_priority():
    source = (
        "The dashboard has several visual cards. "
        "Private by default means personal plans remain hidden "
        "unless explicitly shared. "
        "The footer contains navigation links."
    )

    preview = build_focused_evidence_preview(
        source,
        question="How are personal plans protected?",
        claim_text="",
        matched_terms=(
            "private",
            "plans",
            "shared",
        ),
    )

    assert preview.focused is True
    assert "Private by default" in preview.text
    assert preview.matched_term_count >= 2


def test_configured_limit_is_safely_capped():
    source = "Relevant evidence. " + (
        "More context. " * 200
    )

    preview = build_focused_evidence_preview(
        source,
        question="What evidence is relevant?",
        claim_text="Relevant evidence.",
        max_characters=50_000,
    )

    assert (
        len(preview.text)
        <= MAX_EVIDENCE_PREVIEW_CHARACTERS
    )

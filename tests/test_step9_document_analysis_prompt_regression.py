"""Regression guard for the Step 9 document-analysis prompt template."""

from services.ai_service import _build_document_analysis_prompt


def test_document_analysis_prompt_builds_step9_action_item_schema():
    prompt = _build_document_analysis_prompt(
        filename="document.pdf",
        extracted_text="--- Page 1 ---\nReadable text.",
    )

    assert '"action_items": [' in prompt
    assert '"tags": ["short", "useful", "labels"]' in prompt
    assert '"source": {' in prompt
    assert '"page": 1' in prompt


def test_confirmed_type_prompt_also_builds_without_f_string_errors():
    prompt = _build_document_analysis_prompt(
        filename="paper.pdf",
        extracted_text="--- Page 1 ---\nResearch content.",
        confirmed_document_type="research_paper",
    )

    assert "CONFIRMED DOCUMENT TYPE:" in prompt
    assert '"action_items": [' in prompt

"""Step 14 historical question/analysis status contract tests."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_document_q_and_a_saves_historical_status_for_previous_versions():
    text = (
        ROOT
        / "services"
        / "document_question_workflow_service.py"
    ).read_text(encoding="utf-8")

    assert '"Historical"' in text
    assert "document.is_historical_version" in text
    assert "expected_status=answer_status" in text
    assert "status=answer_status" in text


def test_historical_versions_cannot_create_new_current_analysis():
    text = (
        ROOT
        / "services"
        / "document_ai_workflow_service.py"
    ).read_text(encoding="utf-8")

    assert "document.is_historical_version" in text
    assert "previous document version" in text

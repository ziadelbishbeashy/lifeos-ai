"""Step 13F regression guards for comparison trust boundaries."""

from pathlib import Path


ROOT = Path(
    __file__
).resolve().parents[1]


def test_draft_service_does_not_persist_new_completed_result():
    text = (
        ROOT
        / "services"
        / "document_comparison_draft_service.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "db.session.add" not in text
    assert "Step 13D" in text


def test_only_final_workflow_creates_completed_comparison():
    text = (
        ROOT
        / "services"
        / "document_comparison_workflow_service.py"
    ).read_text(
        encoding="utf-8"
    )

    assert 'status="Completed"' in text
    assert "verify_document_comparison_draft" in text


def test_verifier_has_category_specific_evidence_guards():
    text = (
        ROOT
        / "services"
        / "document_comparison_verifier_service.py"
    ).read_text(
        encoding="utf-8"
    )

    assert '"changed"' in text
    assert '"potential_conflict"' in text
    assert '"added"' in text
    assert '"removed"' in text
    assert "_coverage_supports_absence_claim" in text
    assert "confidence" in text
    assert '"high"' in text


def test_step14_versioning_is_not_implemented_inside_step13_prompt():
    text = (
        ROOT
        / "services"
        / "ai_service.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "Do not claim that B is newer" in text
    assert "Step 14" in text

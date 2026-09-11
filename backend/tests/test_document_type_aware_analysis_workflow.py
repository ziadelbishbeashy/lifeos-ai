"""Workflow tests for confirmed type metadata and fingerprints."""

from services import document_ai_workflow_service as workflow


def test_analysis_fingerprint_changes_with_confirmed_type():
    text = "Same PDF text."

    research = workflow._create_source_fingerprint(
        text,
        confirmed_document_type="research_paper",
    )

    meeting = workflow._create_source_fingerprint(
        text,
        confirmed_document_type="meeting_notes",
    )

    assert research != meeting


def test_analysis_fingerprint_is_stable_for_same_type():
    first = workflow._create_source_fingerprint(
        "Same PDF text.",
        confirmed_document_type="research_paper",
    )

    second = workflow._create_source_fingerprint(
        "Same PDF text.",
        confirmed_document_type="research_paper",
    )

    assert first == second

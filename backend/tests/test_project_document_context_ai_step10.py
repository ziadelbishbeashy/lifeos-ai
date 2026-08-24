"""Step 10 prompt-level project document context tests."""

from services import ai_service


def test_project_context_metadata_counts_current_document_findings():
    context = {
        "project": {
            "id": 3,
            "title": "LifeOS",
        },
        "tasks": [],
        "recent_related_notes": [],
        "documents": [
            {
                "analysis_status": "Current",
                "trusted_analysis": {
                    "requirements": [
                        {
                            "text": "Protect document routes",
                        },
                    ],
                },
            },
        ],
        "context_counts": {
            "documents_considered": 1,
            "documents_with_current_analysis": 1,
            "document_findings_considered": 1,
        },
    }

    meta = ai_service._build_project_context_meta(context)

    assert meta["documents_considered"] == 1
    assert meta["documents_with_current_analysis"] == 1
    assert meta["document_findings_considered"] == 1


def test_note_prompt_uses_only_current_trusted_document_analysis():
    prompt = ai_service._build_note_analysis_prompt(
        title="Project note",
        content="Review the current project requirements.",
        note_type="Project Note",
        project_context={
            "project": {
                "id": 3,
                "title": "LifeOS",
            },
            "tasks": [],
            "recent_related_notes": [],
            "documents": [],
            "context_counts": {},
        },
    )

    assert "trusted_analysis" in prompt
    assert 'analysis_status is "Current"' in prompt
    assert "Stale" in prompt

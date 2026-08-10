"""Step 12 AI prompt tests."""

import json

import services.ai_service as ai_service


def test_project_document_prompt_allows_multiple_files_but_forbids_outside_knowledge(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        ai_service,
        "get_ai_configuration",
        lambda: {"provider": "test", "api_key": "key", "model": "model"},
    )

    def fake_generate_text(**kwargs):
        captured["prompt"] = kwargs["prompt"]
        return json.dumps({
            "found_in_document": True,
            "answer": "",
            "claims": [
                {"text": "The requirement exists.", "source_ids": [1, 2]}
            ],
        })

    monkeypatch.setattr(ai_service, "_generate_text", fake_generate_text)

    result = ai_service.ask_project_documents_question(
        project_title="LifeOS",
        retrieved_context=(
            '[Source 1 | Document "a.pdf" | Page 1]\nRequirement A.\n\n'
            '[Source 2 | Document "b.pdf" | Page 2]\nRequirement B.'
        ),
        question="What is required?",
    )

    assert result["found_in_document"] is True
    assert "Sources may come from different files" in captured["prompt"]
    assert "Do not use outside knowledge" in captured["prompt"]
    assert "When documents disagree" in captured["prompt"]

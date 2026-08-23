"""Step 13C AI service contract tests."""

from services import ai_service


def test_compare_document_evidence_uses_ordered_semantic_prompt(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        ai_service,
        "get_ai_configuration",
        lambda: {
            "provider": "test",
            "api_key": "key",
            "model": "comparison-model",
        },
    )

    def fake_generate_text(**kwargs):
        captured["prompt"] = kwargs["prompt"]

        return """
        {
          "summary": "Password policy changed.",
          "findings": [
            {
              "category": "changed",
              "topic": "Password length",
              "explanation": "The minimum increased.",
              "confidence": "High",
              "document_a": {
                "statement": "Minimum 8",
                "source_ids": ["A1"]
              },
              "document_b": {
                "statement": "Minimum 12",
                "source_ids": ["B2"]
              }
            }
          ]
        }
        """

    monkeypatch.setattr(
        ai_service,
        "_generate_text",
        fake_generate_text,
    )

    result = ai_service.compare_document_evidence(
        document_a_filename="requirements-v1.pdf",
        document_b_filename="requirements-v2.pdf",
        evidence_context=(
            "[A1 | requirement | Page 2]\n"
            "Minimum password length is eight.\n\n"
            "[B2 | requirement | Page 2]\n"
            "Minimum password length is twelve."
        ),
        alignment_context="Likely related evidence pairs:\n- A1 ↔ B2",
    )

    assert result["comparison"]["findings"][0]["category"] == "changed"

    prompt = captured["prompt"]

    assert "Document A is the BASELINE" in prompt
    assert "Document B is compared AGAINST Document A" in prompt
    assert "Rewording with the same meaning is NOT a change" in prompt
    assert "Do not claim that B is newer" in prompt
    assert "A1 ↔ B2" in prompt
    assert "potential_conflict" in prompt


def test_comparison_parser_accepts_no_difference_result(monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "get_ai_configuration",
        lambda: {
            "provider": "test",
            "api_key": "key",
            "model": "comparison-model",
        },
    )

    monkeypatch.setattr(
        ai_service,
        "_generate_text",
        lambda **kwargs: '{"summary":"","findings":[]}',
    )

    result = ai_service.compare_document_evidence(
        document_a_filename="a.pdf",
        document_b_filename="b.pdf",
        evidence_context="[A1] Same rule\n[B1] Same rule",
    )

    assert result["comparison"]["findings"] == []
    assert "No material differences" in (
        result["comparison"]["summary"]
    )

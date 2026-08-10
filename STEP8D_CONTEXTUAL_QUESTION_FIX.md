# Step 8D contextual-question fix

## Problem

A highlighted passage could be correctly supplied as Source 1, but the
answerability verifier still received the literal user question:

    Explain this in simple terms.

The verifier is intentionally strict and treated "this" as an unresolved
reference. It could therefore return `answerable=false` even though Source 1
was the exact passage the user had selected.

## Fix

The stored/user-facing question remains exactly what the user typed.

For the two internal AI stages only:
- answerability verification
- final grounded answer generation

LifeOS now expands the question so the model knows:
- Source 1 is the user's selected passage.
- "this", "it", "here", and "this passage" refer to Source 1.
- Explain/simplify/summarize/clarify requests can be answered directly from
  the selected passage.
- For broader questions, Source 1 is the primary anchor and the other
  retrieved sources from the whole PDF can be used as supporting evidence.

The workflow version is bumped to v11 so old cached no-answer results are not
reused.

## Important behavior

LifeOS still searches the whole PDF. It does not send the entire PDF to the
model. The selected passage is guaranteed context, while the backend retrieves
the most relevant additional passages from the whole document.

Replace:
- services/document_question_workflow_service.py

Add:
- tests/test_document_selected_context_contextual_question.py

No database migration is required.

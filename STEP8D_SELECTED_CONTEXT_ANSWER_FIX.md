# Step 8D selected-context answer fix

Problem:
A highlighted passage was validated against the PDF, but the answer workflow
still depended on mapping that selection back to database chunks. If chunk
mapping returned nothing, or if the user asked a context-dependent question
such as "Explain this", normal retrieval could miss the highlighted passage.
The verifier then returned a fail-closed no-answer result, which was saved with
status Completed.

Fix:
1. The exact verified highlighted text is always inserted as Source 1.
2. Whole-document hybrid retrieval still runs.
3. Retrieval uses both the user's question and the selected passage, allowing
   the system to find related evidence elsewhere in the PDF.
4. Nearby mapped chunks can still be preferred for additional local context.
5. The workflow version is bumped to v10 so previously cached no-answer
   results are not reused.
6. The route no longer shows a success flash when the answer is the deliberate
   no-evidence response.

Behavior:
Selected highlight = guaranteed preferred source.
Whole PDF = still searched for additional relevant evidence.
The AI does not receive the raw entire PDF every time; it receives the selected
passage plus the most relevant verified passages retrieved from the whole PDF.

Replace:
- services/document_question_workflow_service.py
- routes/document_routes.py

Add:
- tests/test_document_selected_context_answer_regression.py

No database migration is required.

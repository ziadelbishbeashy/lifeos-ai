# Step 8D compatibility fix

This patch addresses the final three failures from the 315-pass test run.

1. Stale workflow-version assertion:
   v11 is intentional, so the older regression test now expects v11.

2. Route mock compatibility:
   the route safely reads result.question.answer only when a question object
   exists. Production behavior is unchanged.

3. Preferred-chunk helper compatibility:
   selected_context is optional again. With selected context, the exact verified
   PDF selection remains Source 1. Without it, preferred mapped chunks are
   still placed before ordinary retrieval results.

Replace:
- services/document_question_workflow_service.py
- routes/document_routes.py
- tests/test_document_selected_context_answer_regression.py

Add:
- tests/test_document_selected_context_compatibility.py

No database migration is required.

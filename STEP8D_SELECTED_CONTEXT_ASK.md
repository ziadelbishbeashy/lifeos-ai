# LifeOS Document Brain — Step 8D Selected Context -> Ask Document

This implements the combined B + C flow chosen for PDF text selection.

User flow:
1. Select normal text directly on the rendered PDF page.
2. A tiny floating toolbar appears: Ask about this / Copy.
3. Ask about this closes the PDF and switches immediately to Ask Document.
4. Ask Document shows a visible Selected PDF context card.
5. The selected passage stays highlighted when the PDF is reopened.
6. Remove context clears the card, hidden form fields, and PDF highlight.
7. The question workflow verifies that the selected text really belongs to the
   stated owned PDF page before it is allowed into the RAG prompt.
8. Backend chunks are resolved privately and prepended as preferred evidence,
   while normal hybrid retrieval still runs for additional supporting evidence.
9. The selected context is saved with the question so answer history shows what
   passage the question started from.

No database migration is required.

Files:
- NEW services/document_selected_context_service.py
- UPDATED services/document_question_workflow_service.py
- UPDATED routes/document_routes.py
- UPDATED templates/document_details.html
- UPDATED static/js/document-pdf-viewer.js
- UPDATED static/css/theme-v2.css
- NEW tests/test_document_selected_context_service.py
- NEW tests/test_document_selected_context_workflow.py
- NEW tests/test_document_selected_context_route.py
- NEW tests/test_document_selected_context_ui.py

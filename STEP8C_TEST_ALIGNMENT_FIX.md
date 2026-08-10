# Step 8C Test Alignment Fix

This patch fixes the four failing tests after the intentional Step 8C UX redesign.

Why the failures happened:

1. `test_semantic_pdf_search_route_returns_reader_safe_payload`
   did not request the `user` fixture, so `student@example.com` did not exist
   in the in-memory test database. The login therefore failed and the protected
   route returned HTTP 302.

2. The three old `test_document_search_ui.py` assertions still expected the
   Step 7 developer-style search-result UI:
   - "Search inside this PDF"
   - rendered passage cards
   - "Semantic similarity"
   - "No passages matched this search"

   Step 8C intentionally replaced that UI with the full PDF workspace where
   semantic matches are highlighted directly in the PDF.

This patch updates tests to validate the new intended behavior rather than
re-introducing the old UI.

Files to replace:
- tests/test_document_pdf_semantic_search_route.py
- tests/test_document_search_ui.py

No production code or database migration is required.

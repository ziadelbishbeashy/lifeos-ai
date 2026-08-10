# LifeOS Document Brain — Step 8C: Semantic PDF Highlighting

This patch changes PDF search from developer-shaped result cards into a reader-first PDF experience.

Locked UX choice: B
- Strong semantic matches use a stronger highlight.
- Related matches use a lighter highlight.
- Numerical similarity/rank/chunk information remains backend-only.

New flow:
1. Open the full PDF inside LifeOS.
2. Search for a topic, question, or concept.
3. LifeOS runs the existing exact + keyword + semantic retrieval backend.
4. The browser receives only page/section/passage/emphasis data.
5. Relevant pages get markers in the thumbnail sidebar.
6. Related text is highlighted directly in the selectable PDF.js text layer.
7. Previous/next related-passage controls move through the semantic matches.

The old developer-heavy Search tab has been replaced by a simple PDF workspace entry point. The old server search route remains for compatibility, but the normal UI no longer renders chunk ids, retrieval modes, ranks, scores, or matched-term diagnostics.

Step 8D will use the selectable PDF text layer added here so a user can drag over any passage and choose Ask about this or Copy.

No database migration is required.

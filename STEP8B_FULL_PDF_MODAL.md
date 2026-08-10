# LifeOS Document Brain — Step 8B Full PDF Modal

This patch implements the user's selected full viewer option (C).

Included viewer capabilities:
- Open a cited/search-result page inside a LifeOS modal.
- Open the same PDF/page in a new browser tab.
- Previous/next page navigation and direct page-number input.
- Zoom in/out and Fit Width.
- Rotate left/right.
- Thumbnail sidebar with lazy thumbnail rendering.
- PDF text search with per-page match results.
- Protected download through /documents/<id>/file?download=1.
- Print action.
- Keyboard shortcuts: left/right pages, Ctrl/Cmd+F, +/-, Escape.
- Browser-native PDF viewer fallback if PDF.js cannot start.

PDF.js integration:
- Development build loads pinned pdf.js 5.3.31 from cdnjs.
- The PDF itself is never fetched from a public URL; it still comes from the
  authenticated LifeOS /documents/<id>/file route.
- If the external PDF.js module is unavailable, LifeOS falls back to the
  browser's embedded PDF viewer using the same protected route.
- Before production deployment, we can vendor the chosen PDF.js release into
  static/vendor/pdfjs during the final deployment/security pass.

Step 8B deliberately adds only the Open Page source action. Step 8C/8D will
add the context drawer, copy choices, and Ask About This using the stable
chunk_id added in Step 8A.

No database migration is required.

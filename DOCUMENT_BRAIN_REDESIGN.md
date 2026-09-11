# Document Brain redesign

This revision restructures the React Document Brain workspace without changing backend/API behavior.

## What changed

- Rebuilt `DocumentsPage.tsx` as an application workspace rather than an in-app landing page.
- The document library is now the primary content area.
- Uploading is a compact side panel instead of a large full-width section.
- Documents use readable rows with project, version, date, status and summary context.
- Search, project/status filters and sorting are grouped into one toolbar.
- Rebuilt `DocumentDetailsPage.tsx` with a compact file header, stable tabs and clearer content hierarchy.
- Overview separates focus, attention, actions, questions and document structure.
- Search, Ask AI, actions, PDF and version history each have dedicated layouts.
- Added `styles/document-brain.css` using a new `brain-*` namespace.

## CSS isolation

The rebuilt Document Brain pages no longer use the old `db-*` page classes or the older Document Brain layout classes. The new namespace prevents the legacy Document Brain rules in `theme-v2.css` from competing with this layout.

## Validation

- TypeScript/TSX syntax transpilation: passed for both rebuilt pages.
- CSS contract check: passed.
- New stylesheet brace/syntax structure check: passed.
- Full dependency build was not run because this working environment does not contain the project's npm dependencies.

# LifeOS Document Brain — Phase 2 UI

This patch completes the full Document Brain UI enhancement phase.

## Included

### 2.1 Document library redesign
- Hero and workspace metrics
- Drag-and-drop PDF upload
- Selected-file validation and preview
- Search, project filter, status filter and sorting
- Grid/list view with saved preference
- Document readiness, analysis and question metrics

### 2.2 Document details header
- Breadcrumbs and connected project access
- Document status badges
- Search-index, analysis and Q&A snapshots
- Primary analyse/reanalyse actions

### 2.3 Analysis interface
- Overview, Insights, Actions and Ask Document tabs
- Executive summary and purpose card
- Insight search
- Collapsible requirements, decisions, deadlines, risks and open questions

### 2.4 Ask Document interface
- Grounded question composer
- Suggested prompts and character counter
- Chat-style saved answer cards
- Re-ask and copy-answer controls

### 2.5 Answer and source cards
- Focused excerpt labels
- Source number, page and section metadata
- Expandable supporting-source area

### 2.6 Question history
- Search and status filters
- Saved-answer counts
- Completed and failed states
- Source-aware answer presentation

### 2.7 Loading, empty and error states
- Inline form state
- Existing global loading overlay integration
- Analysis, OCR, no-result and provider-error states
- Confirmation modal integration for destructive/repeated actions

### 2.8 Mobile consistency
- Responsive library cards
- Scrollable tabs and filters
- Mobile action dock
- Single-column analysis, actions and Q&A layouts
- Reduced-motion support

## Replace these project files

```text
routes/document_routes.py
templates/documents.html
templates/document_details.html
static/css/theme-v2.css
```

Add these new files:

```text
static/js/document-brain-ui.js
tests/test_document_brain_ui.py
```

No database migration is required.

## Validation

```powershell
python -m py_compile routes\document_routes.py
node --check static\js\document-brain-ui.js

python -m pytest tests\test_document_brain_ui.py -v
python -m pytest
```

Restart Flask and hard refresh the browser:

```powershell
python app.py
```

Use `Ctrl + Shift + R` after the server restarts so the new CSS and JavaScript are loaded.

## Expected user flow

```text
Document library
→ upload or open a PDF
→ analyse it
→ review structured insights
→ approve or reject actions
→ ask grounded questions
→ inspect focused supporting excerpts
```

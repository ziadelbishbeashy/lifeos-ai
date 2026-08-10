# LifeOS Document Brain — Step 5

## Structured Document Overview

Step 5 turns a saved AI analysis into one stable Document Brain dashboard.

### Backend flow

1. `analyze_document()` asks the configured provider for a structured JSON analysis.
2. `normalise_document_analysis()` converts current and legacy response shapes into one canonical schema.
3. `analyse_owned_document()` saves the canonical result and creates reviewable task suggestions.
4. `build_structured_document_overview()` prepares safe section counts and dashboard metadata for the route.
5. `document_details.html` renders the executive summary and all supported structured sections.

### Canonical sections

- Key points
- Requirements
- Decisions
- Risks
- Deadlines
- Action items
- Missing information
- Questions to explore

`missing_information` records gaps that require clarification. `questions` contains useful grounded questions that the current document can answer.

### Compatibility and safety

- Supports strings, lists and structured objects from older saved analyses.
- Supports common legacy aliases such as `overview`, `main_points`, `needs`, `actions` and `suggested_questions`.
- Invalid dates and page numbers remain unset instead of being guessed.
- Unknown document types become `General Reference`.
- Empty categories remain empty arrays.
- The analysis fingerprint includes `structured-document-overview-v2`, so old generic analyses are not silently reused.
- A database or suggestion-building failure rolls back the incomplete analysis and records a failed attempt.

### Database changes

No database migration is required. The canonical structure remains stored in `DocumentAIAnalysis.insights_json`.

### Validation commands

```powershell
python -m py_compile `
    services\document_analysis_service.py `
    services\document_overview_service.py `
    services\ai_service.py `
    services\document_ai_workflow_service.py `
    routes\document_routes.py

python -m pytest `
    tests\test_document_analysis_service.py `
    tests\test_document_overview_service.py `
    tests\test_ai_service_document.py `
    tests\test_document_ai_workflow_service.py `
    tests\test_document_brain_ui.py `
    -v

python -m pytest
```

Restart Flask and analyse an existing PDF again. The schema-versioned fingerprint will create a new Step 5 analysis rather than reuse the previous generic analysis.

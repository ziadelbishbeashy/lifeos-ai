# LifeOS Document Brain — Step 10: Connect Documents to Project Context

## Goal

Step 10 connects trusted Document Brain findings to the existing shared project
context service.

A project context can now carry current, page-aware document intelligence:
- key findings
- requirements
- decisions
- risks
- deadlines
- reviewable action items
- missing information

This does not create tasks or modify project data.

## Trust and ownership behavior

- The project is checked against `Project.user_id` at the shared context service
  boundary.
- Document queries are scoped through that owned project.
- Only `DocumentAIAnalysis` rows belonging to the same user are considered.
- A completed analysis is exposed as `trusted_analysis` only when its saved
  source fingerprint still matches the document's current extracted text.
- Stale analyses are labeled `Stale`; their structured findings are not exposed
  as current project truth.
- Documents without a valid completed analysis are labeled `Not analysed`.

## Context additions

Each project document keeps its old preview fields for backward compatibility
and adds:

- `analysis_status`
- `has_current_analysis`
- `trusted_analysis`

`trusted_analysis` contains compact page-aware requirements, decisions, risks,
deadlines, key points, action items, and missing information.

Shared `context_counts` now also reports:
- total_project_documents
- documents_considered
- documents_limited
- documents_with_current_analysis
- documents_with_stale_analysis
- documents_without_analysis
- document_findings_considered

## AI integration

The existing project-aware Note/AI Note prompts already receive shared project
context. Step 10 now explicitly tells them to:

- use `trusted_analysis` only when analysis_status is Current;
- never promote Stale/Not analysed findings into current truth;
- preserve current document requirements and decisions as project constraints;
- keep current task status as the operational source of truth for work progress.

This prepares the same shared context for Ask Project / Ask LifeOS later.

## Files

Replace:
- services/workspace_context_service.py
- services/ai_service.py

Add:
- tests/test_project_document_context_step10.py
- tests/test_project_document_context_ai_step10.py

## Database impact

None. No migration is required.

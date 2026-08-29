# I11 — Expanded Ask LifeOS Coverage

I11 connects common workspace questions to deterministic, ownership-safe executors instead of leaving them as route-only intents.

Supported verified intents:

- `today_focus` — “What should I do today?”
- `task_status` — overdue, blocked, open, and due-soon task questions
- `deadline_review` — upcoming task + project deadlines
- `document_review` — current documents with stale or missing structured analysis
- `workspace_gaps` — verified missing-information, stale-analysis, and missing-next-action gaps
- `study_next` — ranks unfinished Module lectures using lecture state and linked task urgency
- `project_question` — deterministic project status/progress/phase/priority/goal/date facts

Existing I8/I10 flows remain unchanged: project/portfolio focus, project review, and recent activity.

## Trust boundary

I11 does not use an LLM for these factual workspace queries. Results come from authenticated LifeOS state and existing ownership-safe domain services. Every response is read-only and marked `verified_from_state`.

## Product payload

Ask LifeOS responses may include an `insight` object with a bounded list of structured items. The frontend renders those items as compact verified cards rather than duplicating the full result in prose.

## No migration

I11 adds no tables and requires no Alembic migration.

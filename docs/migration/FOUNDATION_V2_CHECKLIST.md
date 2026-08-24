# Foundation V2 migration checklist

## Gate 1 — freeze and prove the old behavior

- Run the existing full pytest suite from `backend/`.
- Save the result as the Foundation V2 baseline.
- Smoke-test login, projects, tasks, notes, Document Brain, comparison and
  document versioning in the legacy UI.

## Gate 2 — PostgreSQL

- Start local PostgreSQL with `docker compose up postgres -d`.
- Use the current SQLAlchemy metadata to create a disposable development schema.
- Run database-heavy integration tests against PostgreSQL.
- Fix any dialect assumptions in application code.
- Create and review a frozen PostgreSQL baseline migration.
- Only then migrate existing SQL Server data that must be preserved.

## Gate 3 — Neon

- Create Neon development and staging databases.
- Configure `DATABASE_URL` and `DATABASE_DIRECT_URL` only in backend secrets.
- Rehearse schema bootstrap/migration in staging.
- Validate connection loss/retry behavior and backups before production.

## Gate 4 — service reliability

Split large change surfaces without behavior changes, beginning with:

1. `services/ai_service.py`
2. `routes/document_routes.py`
3. `services/document_question_workflow_service.py`
4. `models.py` only after PostgreSQL baseline is frozen

Every extraction must have compatibility tests before deleting the old import.

## Gate 5 — React

Migrate one complete vertical slice at a time:

1. authentication/session contract
2. projects
3. tasks
4. notes
5. Document Brain
6. analytics/focus/notifications

A legacy Jinja screen is removed only after the React equivalent has API,
authorization and regression coverage.

## Gate 6 — resume roadmap

After the reliability gates:

- Step 15 OCR
- Step 16 tables
- Step 17 collections
- Modules + Lectures
- Step 18 RAG evaluation
- Step 19 prompt-injection/security hardening
- Step 20 limits/cost controls

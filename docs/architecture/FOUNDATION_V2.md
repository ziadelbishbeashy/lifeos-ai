# LifeOS Foundation V2

## Decision

LifeOS remains a **modular Flask monolith** for the backend. React + TypeScript is
introduced as a separate frontend and migrates one domain at a time. PostgreSQL
is the canonical database family; Neon is the preferred hosted PostgreSQL target.

The migration intentionally avoids a big-bang rewrite.

## Repository

```text
LifeOS_Foundation_V2/
├── backend/
│   ├── lifeos/
│   │   ├── api/v1/          versioned JSON boundary
│   │   ├── core/            app infrastructure/config/database/extensions
│   │   ├── domains/         business-domain boundaries
│   │   └── shared/          shared AI/storage/jobs infrastructure
│   ├── routes/              legacy Jinja routes during migration
│   ├── services/            existing proven services during stabilization
│   ├── templates/           existing UI; removed only after React parity
│   ├── migrations/          historical SQL Server migration chain
│   └── tests/
├── frontend/                React + TypeScript + Vite
├── database/                DB migration/infrastructure documentation
├── infra/                   deployment/provider guidance
├── docs/                    architecture decisions and migration plan
└── docker-compose.yml       local PostgreSQL + backend
```

## Safety invariants

1. Existing user workflows remain available while architecture changes.
2. React never accesses PostgreSQL/Neon directly.
3. API routes are thin; business decisions stay in domain/service code.
4. New code imports through `lifeos.*` boundaries where possible.
5. Existing `models.py` is not physically split until the PostgreSQL baseline is
   proven. Moving model classes during a DB-engine migration would create two
   sources of schema churn at once.
6. Historical SQL Server migrations remain preserved but are not replayed on a
   fresh PostgreSQL database.
7. No feature is deleted because its React replacement is incomplete.
8. AI provider calls remain behind shared provider boundaries.
9. OCR and other long work must use workers/jobs rather than blocking requests.

## What changed now

- The repository is split into `backend/`, `frontend/`, `database/`, `infra/`,
  and `docs/`.
- The real Flask app factory moved to `backend/lifeos/application.py`.
- `backend/app.py`, `database.py`, `config.py`, and `extensions.py` are compatibility
  entry points so existing tests/imports keep working.
- A versioned `/api/v1` boundary exists.
- PostgreSQL/psycopg is the primary database dependency.
- SQL Server driver support is isolated to an optional legacy requirements file.
- A React + TypeScript migration shell exists and proxies `/api` to Flask in dev.
- Domain facades now provide stable import boundaries without rewriting proven
  service logic in the same change.

## What is deliberately NOT rewritten in this change

- The 100+ existing Flask tests.
- Document Brain algorithms and prompts.
- Existing Jinja screens.
- The physical `models.py` class definitions.
- Historical SQL Server Alembic revisions.

Those are stabilized/migrated in controlled follow-up passes rather than being
silently reimplemented.

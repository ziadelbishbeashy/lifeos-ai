# Foundation V2 change manifest

## Preserved from the supplied project

All existing feature code, templates, static assets, migrations, workers,
storage abstractions, AI providers and tests were copied into `backend/`.

No Step 1–14 Document Brain feature was intentionally removed.

## Compatibility entry points changed

- `backend/app.py` now delegates to `lifeos.application.create_app`.
- `backend/config.py` delegates to `lifeos.core.config`.
- `backend/database.py` delegates to `lifeos.core.database`.
- `backend/extensions.py` delegates to `lifeos.core.extensions`.

This keeps old imports and the existing test suite valid while giving new code a
stable package boundary.

## New backend boundaries

- `lifeos/api/v1/` — versioned JSON API
- `lifeos/core/` — config/database/extensions
- `lifeos/domains/` — auth, projects, tasks, notes, documents and reserved modules
- `lifeos/shared/` — AI, storage and job infrastructure boundaries

## Database direction

- `psycopg` is now the primary database driver dependency.
- SQL Server `pyodbc` moved to `requirements-legacy-sqlserver.txt`.
- existing SQL Server environment variables remain supported temporarily.
- production defaults to requiring PostgreSQL.
- Neon direct migration URL support is added.
- a guard prevents accidentally replaying the legacy SQL Server Alembic chain
  onto an empty PostgreSQL database.

## Frontend

A React + TypeScript + Vite application has been added in `frontend/`. It is a
migration shell, not an unsafe rewrite of every screen. Existing Jinja screens
remain canonical until each vertical slice has API and regression parity.

## Reliability infrastructure

- PostgreSQL portability scanner
- disposable PostgreSQL schema smoke script
- GitHub CI for backend tests, Postgres schema smoke and React build
- baseline archive SHA-256 record
- migration and architecture runbooks

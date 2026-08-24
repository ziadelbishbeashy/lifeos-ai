# Database boundary

LifeOS Foundation V2 targets **PostgreSQL**. Neon is a hosted PostgreSQL provider,
not a separate application layer.

Application code and Alembic remain owned by `backend/`. This folder contains
infrastructure/migration guidance only.

- `postgres/` — the target database family.
- `legacy-sqlserver/` — temporary migration notes for the previous database.

The React frontend must never receive database credentials or connect to the
database directly.

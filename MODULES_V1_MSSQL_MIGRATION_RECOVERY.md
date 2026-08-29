# Modules V1 — SQL Server migration recovery

The Modules V1 migration previously created `ix_documents_user_id` before changing
`documents.user_id` from nullable to `NOT NULL`. Microsoft SQL Server rejects
`ALTER COLUMN` while an index depends on that column, producing error 5074/4922.

Revision `20260828_0003` now temporarily removes dependent SQL Server indexes and
foreign keys before nullability changes, restores them afterwards, and safely
skips Module tables that may already exist because local `db.create_all()` was
run before Alembic.

Revision `20260828_0004` keeps the same dependency-safe behavior as a repair layer
for installations that were already partially/stale at 0003.

From `backend` run:

```powershell
python -m flask --app app db current
python -m flask --app app db heads
python -m flask --app app db upgrade
python -m flask --app app db current
```

Expected final revision:

```text
20260828_0004 (head)
```

Do not delete the existing SQL Server database to recover from this migration.

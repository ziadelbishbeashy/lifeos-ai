# LifeOS Architecture Step 3 — Migration Baseline

This checkpoint introduces a controlled Flask-Migrate/Alembic history without
changing the current SQL Server schema.

## What changes

- Adds a migration repository.
- Adds an empty baseline revision for the existing database.
- Adds migration foundation tests.
- Keeps `db.create_all()` available only for local development and tests.
- Includes the confirmed CSRF time-limit compatibility fix.

## Existing database setup

Back up the database first, then run once:

```powershell
python -m flask --app app db stamp 20260726_0001
python -m flask --app app db current
```

Expected current revision:

```text
20260726_0001 (head)
```

The stamp command records migration history only. It does not modify LifeOS
application tables or user data.

## Validation

```powershell
python -m pytest
python app.py
```

Test login, projects, tasks, notes, focus mode, and analytics.

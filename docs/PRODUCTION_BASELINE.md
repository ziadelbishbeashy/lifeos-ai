# LifeOS Production Baseline

## Web Process

- Development entry point: `python app.py`
- Production WSGI entry point: `wsgi:app`
- Container command: Gunicorn using `gunicorn.conf.py`
- Liveness endpoint: `/health`
- Database-readiness endpoint: `/health/ready`

## Configuration

Production requires:

- `LIFEOS_ENV=production`
- A unique `SECRET_KEY` of at least 32 characters
- A valid database connection
- Secure HTTPS cookies
- Proxy-header handling at the trusted hosting boundary

Secrets belong in environment variables or a deployment secret store, never in
Git or ZIP uploads.

## Storage

The active development adapter is local file storage under `instance/storage`.
Feature code should use `storage.get_storage()` instead of writing directly to
public static directories. A cloud adapter can later implement the same
contract.

## Background Work

The current foundations support inline and in-memory jobs for architecture
work and tests. Heavy public workloads must later use a durable queue adapter.
The standalone notification worker is separated from the Flask web process.

## Database Changes

All future schema changes must use reviewed Flask-Migrate/Alembic revisions.
The application must not rely on `db.create_all()` to upgrade a public database.

## Release Gate

Before a public beta:

- Full tests pass
- Production configuration validation passes
- Database migration is reviewed and applied to staging
- Upload validation and ownership checks are tested
- Backup and restore are verified
- Logs and health probes are monitored
- AI usage and provider failures are handled gracefully

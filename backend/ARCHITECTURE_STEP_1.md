# LifeOS Architecture Refactor — Step 1

This checkpoint reorganises the existing application without replacing the
project or changing its product features.

## What changed

- Added a Flask `create_app()` application factory.
- Added separate development, testing, and production configuration classes.
- Centralised Flask extensions in `extensions.py`.
- Moved landing/dashboard route logic out of `app.py` while preserving the
  original endpoint names.
- Added a `/health` endpoint for future Azure monitoring.
- Added a production WSGI entry point in `wsgi.py`.
- Added initial smoke tests.
- Added a safe `.env.example` template.
- Kept `python app.py` as the normal local start command.

## Local start

```bash
pip install -r requirements.txt
python app.py
```

## Optional tests

```bash
pytest
```

## Important

- Keep your real `.env` file locally; never upload or commit it.
- The email scheduler still runs only when explicitly enabled.
- Public deployment should use database migrations rather than `db.create_all()`.
- CSRF protection and route/service separation are planned for the next
  controlled checkpoint after this version is confirmed working locally.

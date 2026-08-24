# Validation performed while packaging

Performed in the artifact environment:

- copied every file from the supplied latest project into `backend/`
- preserved all 108 existing `test_*.py` files
- preserved all 56 existing service modules
- Python `compileall` passed for the complete backend after the architecture changes
- PostgreSQL portability static guard passed
- JSON files parse successfully
- repository structure/provenance was checked before packaging

The artifact environment does not contain the Flask project dependencies and has
no package-network access, so the full pytest suite and React `npm build` could
not be executed here. The repository includes CI jobs for both, plus a disposable
PostgreSQL schema smoke test.

Run locally before making Foundation V2 the active branch:

```powershell
cd backend
pip install -r requirements-dev.txt
python scripts\check_postgres_portability.py
python -m pytest
```

Then:

```powershell
cd ..\frontend
npm install
npm run build
```

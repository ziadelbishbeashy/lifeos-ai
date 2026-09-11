# LifeOS Architecture Step 4 — Authentication Module Refactor

This checkpoint moves authentication business rules out of the Flask route
module while preserving the current pages, endpoint names, database schema,
and user experience.

## Included

- New `services/auth_service.py` service layer
- Normalised email and registration validation in one place
- Transaction-safe account creation
- Preserved legacy-project ownership behaviour
- Simplified authentication routes
- Safe external redirect protection retained
- Expanded authentication service and route tests
- Compatibility shim for the old `services/auth_routes.py` path

## Not included yet

- Email verification
- Password reset
- Google or Microsoft sign-in
- Login rate limiting
- New database columns

These require separate reviewed checkpoints.

## Commands

```powershell
python -m pytest
python app.py
```

## Manual checks

- Register a temporary account only when using a test database
- Log in and log out with the existing account
- Confirm the dashboard still requires authentication
- Confirm Projects, Tasks, Notes, Focus Mode, and Analytics still open

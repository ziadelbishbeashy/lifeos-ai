# LifeOS Architecture Step 6 — Tasks Refactor

This checkpoint moves task business rules and persistence out of the Flask
routes while preserving the existing URLs, templates, database schema, and
user experience.

## Added

- `services/task_service.py`
- Task input normalisation and validation
- Ownership-safe task and project lookups
- Reminder and recurrence validation
- Task overview calculations
- Transaction-safe create, update, toggle, and delete operations
- Task service and route tests

## Changed

- `routes/task_routes.py` now handles HTTP concerns and delegates task rules to
  the service layer.

## Not changed

- Database schema
- Existing task URLs and endpoint names
- Templates and JavaScript
- Recurring-task behaviour
- Reminder behaviour
- Existing user data

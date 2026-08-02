# LifeOS Model Boundaries

The current `models.py` remains unchanged during the architecture refactor so the
existing SQL Server database stays compatible.

Business code must access models through services:

- `auth_service.py` — users and authentication
- `project_service.py` — projects
- `task_service.py` — tasks and recurrence state
- `note_service.py` — notes, analyses, questions, and AI task suggestions
- `focus_service.py` — focus sessions and distractions
- `notification_preferences_service.py` — notification settings and history
- `document_access_service.py` — temporary ownership boundary for legacy documents

The future Document Brain migration must add direct document ownership, storage
metadata, processing status, visibility, checksums, and extracted-content
references before general document uploads are enabled.

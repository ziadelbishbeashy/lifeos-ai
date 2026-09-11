# I16 — Structured Memory

LifeOS memory is a controlled intelligence layer, not a hidden conversation log.

## Persisted memory types

- `current_focus` — explicit user-set focus; one active value at a time.
- `preference` — explicit workspace preference, optionally scoped to a project.
- `recent_project` — safe derived pointer to recently active owned projects; expires automatically.
- `dismissed_suggestion` — expiring record of a proactive notice the user explicitly dismissed.

## Trust contract

- No raw chat transcript is stored as I16 memory.
- No raw document/PDF text is stored as I16 memory.
- No automatic personal-profile inference is persisted.
- User-created memory is visible and deletable from `/memory`.
- Clearing memory deletes memory rows only; projects, tasks, notes and documents are untouched.
- Explicit preferences/current focus can enter the verified project context as typed `memory.*` facts, so the existing claim verifier can audit any AI use of them.
- Dismissed proactive suggestions are remembered for a bounded period so I15 does not immediately re-surface the same suggestion.

## API

- `POST /api/v1/intelligence/memory/refresh`
- `GET /api/v1/intelligence/memory`
- `POST /api/v1/intelligence/memory`
- `DELETE /api/v1/intelligence/memory/<id>`
- `POST /api/v1/intelligence/memory/clear`

## Database

Migration head: `20260829_0004`

New table: `lifeos_memories`

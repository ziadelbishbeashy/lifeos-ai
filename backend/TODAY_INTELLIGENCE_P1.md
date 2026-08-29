# P1 — Intelligence-powered Home / Today

LifeOS Home now reuses the constrained I8 Project Review Agent to create a
read-only, deterministic attention view for the authenticated user.

## Trust rules

- No LLM call is required to render Today.
- Only owned projects/resources are reviewed.
- The service reuses the same bounded I8 project context and resource limits.
- Results are recommendations over trusted state; nothing is mutated.
- If the intelligence endpoint is unavailable, the existing dashboard focus
  task remains as the UI fallback.

## API

`GET /api/v1/intelligence/today`

The payload contains a bounded ranked priority list, evidence references,
summary, attention level, and `verified_from_state=true` / `read_only=true`.

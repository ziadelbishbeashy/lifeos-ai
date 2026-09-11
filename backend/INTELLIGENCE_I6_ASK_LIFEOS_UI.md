# LifeOS Intelligence I6 — Ask LifeOS surface + efficient verified context

This slice turns the verified I1-I5 pipeline into a real product surface without
changing its trust boundary.

## Product surface

- `/ask` is the first dedicated Ask LifeOS page.
- It uses `POST /api/v1/intelligence/ask`.
- It shows whether the answer was independently AI-verified or returned from the
  deterministic trusted-state fallback.
- It shows the resolved project scope and attention level.
- It remains read-only. Unsupported intents are not guessed.

## Efficiency changes

1. Ask LifeOS now gathers the project tool/context snapshot once. The
   deterministic project review is derived from the same authorized snapshot
   instead of re-running the tool plan a second time.
2. The reasoner receives compact typed `key/value/fact_type/confidence` facts,
   not repeated evidence/provenance objects or recent activity that the current
   project-review answer does not use.
3. The independent verifier receives only authoritative fact key/value pairs,
   reviewed support statements, and candidate reasoning. Full provenance stays
   inside LifeOS for audit and deterministic checks.
4. Complex project review still keeps two AI boundaries (reasoner + independent
   prose verifier). Reliability is not traded away just to reduce API calls.

## Next intelligence work

The next safe extension is to add reviewed read-only executors for routed intents
such as `task_status`, `project_question`, and `recent_activity`, then connect a
constrained Project Review Agent that can inspect more signals but still only
propose actions.

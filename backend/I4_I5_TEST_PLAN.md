# LifeOS Intelligence I4/I5 test plan

Run from `backend/`:

```powershell
python -m pytest tests -k "intelligence or project_review" -v
python -m pytest tests -q
```

Then smoke-test the real configured provider:

```powershell
python -m flask --app app intelligence-ask `
  --user-id 1 `
  --query "How is my LifeOS project going?"
```

Expected properties:

- intent resolves to `project_review` and the owned project;
- `response_mode` is `ai_verified` when both reasoning + verifier complete;
- factual claims match the trusted context values;
- manual project progress is not confused with task completion;
- stale document analysis is never treated as current document evidence;
- no database/tool/provider internals are surfaced in the normal `/ask` API;
- provider or verifier failure produces `deterministic_fallback`, not an
  unverified AI answer;
- workflow remains read-only.

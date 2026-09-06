# Ask LifeOS Model Selector Privacy Hotfix

Apply after `lifeos-ai-ask-lifeos-model-selector-patch.zip`.

## Fix
- Keeps `model_tier` as an internal/request-side routing field.
- Public `/api/v1/intelligence/ask` response now exposes `reasoning_tier` instead of `model_tier`.
- Preserves the longstanding public API contract that provider/model implementation details are not serialized.
- Frontend Fast / Balanced / Deep chips now read `reasoning_tier`.
- Goal reviews continue to send the selected internal `model_tier` override to the backend.

## No changes
- No database migration.
- No model-router behavior changes.
- No LangSmith changes.
- No RAG/I9 changes.
- No `frontend/public`.

## Verify
Backend:
`py -3.11 -m pytest tests\\test_intelligence_ask_api_i4_i5.py -q`
`py -3.11 -m pytest tests\\test_ask_lifeos_model_selector.py -q`
`py -3.11 -m pytest -q`

Frontend:
`npm run build`
`npm run css:check`

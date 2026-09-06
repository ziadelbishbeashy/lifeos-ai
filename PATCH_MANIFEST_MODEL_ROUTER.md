# LifeOS AI Model Router — Patch Manifest

## Purpose
Add a deterministic CHEAP / NORMAL / DEEP model-selection layer without changing
LifeOS domain services, Document Brain retrieval, I9 confirmation, database writes,
or provider fallback architecture.

## Routing rules
- CHEAP: `document_type_detection`, `document_answerability`
- NORMAL: `ai_service.*`, `document_comparison_verifier`,
  `ask_lifeos_claim_verifier`, `ask_lifeos_reasoner`,
  `academic_schedule_extraction`, and every unknown/new feature
- DEEP: `agent_reasoning`

The router itself makes **zero AI calls**. It only chooses a configured model name.

## Safe rollout
By default, a tier with no tier-specific model configured inherits the model the
feature already used. This means applying the patch does not automatically lower
model quality.

To test a cheaper Gemini tier after the patch passes locally, add to `backend/.env`:

```env
AI_MODEL_ROUTER_ENABLED=true
GEMINI_CHEAP_MODEL=gemini-2.5-flash-lite
GEMINI_NORMAL_MODEL=gemini-2.5-flash
GEMINI_DEEP_MODEL=gemini-2.5-flash
```

For an instant rollback:

```env
AI_MODEL_ROUTER_ENABLED=false
```

For future OpenAI deployment the same LifeOS feature code can use:

```env
OPENAI_CHEAP_MODEL=...
OPENAI_NORMAL_MODEL=...
OPENAI_DEEP_MODEL=...
```

## Observability
- Actual selected model continues to be stored in `AIUsageEvent.model`.
- LangSmith generation spans now include model tier, requested model, and whether
  the call was routed to a different model.
- Analytics -> AI Usage (Development) shows the router tier configuration and
  models actually used by feature/operation.

## Files
- `backend/ai/model_router.py` (new)
- `backend/ai/provider_router.py`
- `backend/services/langsmith_observability_service.py`
- `backend/services/ai_usage_service.py`
- `backend/lifeos/api/v1/ai_usage.py`
- `backend/.env.example`
- `backend/tests/test_ai_model_router.py` (new)
- `backend/tests/test_ai_provider_router.py`
- `backend/tests/test_langsmith_observability.py`
- `frontend/src/pages/AnalyticsAiUsagePage.tsx`

## Database
No Alembic migration. Expected head remains `20260906_0001`.

## Local verification

```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\backend
py -3.11 -m pytest tests\test_ai_model_router.py -q
py -3.11 -m pytest tests\test_ai_provider_router.py -q
py -3.11 -m pytest tests\test_langsmith_observability.py -q
py -3.11 -m pytest -q

cd ..\frontend
npm run build
npm run css:check
```

Then open Analytics -> AI Usage (Development) and confirm the Model Router panel
shows CHEAP/NORMAL/DEEP. If `GEMINI_CHEAP_MODEL` is configured, run document type
detection and verify its feature row/LangSmith trace uses the cheap model.

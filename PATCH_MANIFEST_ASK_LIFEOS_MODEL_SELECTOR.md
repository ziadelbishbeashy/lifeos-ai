# LifeOS Ask LifeOS Model Selector — Patch Manifest

## Purpose
Add a provider-agnostic Fast / Balanced / Deep selector directly inside the existing Ask LifeOS composer.

## User-facing behavior
- **Fast** -> requests the CHEAP model tier for the main answer/reasoning call.
- **Balanced** -> requests the NORMAL model tier and is the default UI choice.
- **Deep** -> requests the DEEP model tier for difficult reasoning/agent goals.
- Each assistant response shows the tier used as a small Fast / Balanced / Deep chip.
- Complex I19 goal execution reuses the tier selected when the goal plan was created.

## Cost + trust rules
- The selector does **not** force an LLM call. Deterministic Ask LifeOS routes still use deterministic code at zero model cost.
- User tier overrides apply only to primary user-facing reasoning/answer generation:
  - `ask_lifeos_reasoner`
  - `agent_reasoning`
  - `ai_service.ask_*` grounded answer generation
- Trust/safety helper calls keep their reviewed feature tier and are not downgraded by Fast:
  - claim verification stays NORMAL
  - document answerability keeps its normal router policy (CHEAP)
  - I9 confirmation is unchanged
- No provider/model names are hard-coded into the Ask LifeOS UI.

## Backend
- Adds a request-scoped `ContextVar` model-tier override to `ai.model_router`.
- `/api/v1/intelligence/ask` accepts optional `model_tier` (`cheap|normal|deep`; friendly aliases `fast|balanced|deep` also accepted).
- `/api/v1/intelligence/goal-runs` accepts the same tier so I19 execution honors the originating Ask mode.
- Invalid tiers return the existing validation boundary rather than silently falling back.
- LangSmith LLM spans include `lifeos_model_tier_source=user_override|feature_default`.
- Ask LifeOS root traces include the requested tier as metadata only.

## Database
No Alembic migration. Expected head remains `20260906_0001`.

## Environment
The selector uses the existing Model Router configuration. Example:

```env
AI_MODEL_ROUTER_ENABLED=true
GEMINI_CHEAP_MODEL=gemini-2.5-flash-lite
GEMINI_NORMAL_MODEL=gemini-2.5-flash
GEMINI_DEEP_MODEL=gemini-2.5-flash
```

The DEEP tier can later point at a stronger Gemini/OpenAI model without changing the React UI.

## Files
- `backend/ai/model_router.py`
- `backend/ai/provider_router.py`
- `backend/services/langsmith_observability_service.py`
- `backend/services/intelligence_ask_service.py`
- `backend/lifeos/api/v1/intelligence.py`
- `backend/tests/test_ai_model_router.py`
- `backend/tests/test_ask_lifeos_model_selector.py` (new)
- `frontend/src/pages/AskLifeOSPage.tsx`
- `frontend/src/styles/ux-refresh.css`

## Local verification

```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\backend
py -3.11 -m pytest tests\test_ai_model_router.py -q
py -3.11 -m pytest tests\test_ask_lifeos_model_selector.py -q
py -3.11 -m pytest tests\test_agentic_ask_lifeos_i19.py -q
py -3.11 -m pytest -q

cd ..\frontend
npm run build
npm run css:check
```

## Manual checks
1. Ask a deterministic question in Deep mode, such as `Which tasks are overdue?`; it should remain deterministic.
2. Set `GEMINI_CHEAP_MODEL` to Flash-Lite and ask an AI-reasoned question in Fast mode; LangSmith should show `lifeos_model_tier=cheap` and `lifeos_model_tier_source=user_override` on the primary generation span.
3. Ask the same AI-reasoned question in Balanced and Deep; verify the configured tier model is used.
4. Start a complex goal review after selecting a tier; I19 `agent_reasoning` should use that same selected tier.
5. Confirm claim-verifier spans are still feature-default rather than user-overridden.

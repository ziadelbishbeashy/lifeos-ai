# LifeOS General Intelligence Layer — Updated Patch

Date: 2026-09-09
Patch type: cumulative patch-only overlay for `lifeos-ai-feature-hybrid-rag (16)(1)`
Database: Neon/PostgreSQL
Expected Alembic head: `20260906_0001` (unchanged; no migration added)

## Architecture preserved

- One Ask LifeOS intelligence core; no duplicate Tutor intelligence stack.
- React/TypeScript/Vite remains frontend-only; Flask/backend remains API/services/database/AI.
- Existing Document Brain/RAG pipeline remains authoritative for document knowledge.
- Exact arithmetic uses the deterministic AST allow-list calculator; no `eval`/`exec`.
- Public web research is provider-hosted and read-only.
- Workspace mutations remain read-only planning/review first, then I9 proposal + explicit confirmation; the AI does not write directly to the DB.
- Existing ownership, provenance, evidence, history, failure states, provider budgets and LangSmith metadata-only boundaries are preserved.

## Completed in this continuation

1. Strengthened general request/capability routing.
   - The acceptance wording `Explain binary search with Python code and complexity equations` now explicitly selects generated-code output without forcing web research.
   - Domain-specific permanent intents were not added.
2. Strengthened capability failure behavior.
   - Requests that require selected document/RAG evidence now fail closed when no evidence is retrievable instead of falling through to unsupported model knowledge.
   - Web/calculator failure messages use the matching capability warning.
3. Strengthened web privacy and source safety.
   - Added common environment-secret detection (`DATABASE_URL`, `DB_URL`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `JWT_SECRET`, etc.).
   - Secret-bearing requests are rejected before provider routing.
   - Public source URLs reject credentials, localhost, `.local`, private/loopback/link-local/reserved IP targets.
   - Selected LifeOS context labels are still not silently copied into public queries.
4. Strengthened evidence verification.
   - If web research or document evidence was supplied, generated reasoning must include corresponding source-bound claims/citations.
5. Clarified mutation/I9 behavior.
   - `Create tasks for the fixes` with project context produces a read-only goal plan; the response explicitly states that any later workspace change must become an I9 proposal and requires explicit confirmation.
6. Finished Ask LifeOS rich-response details without redesigning the page.
   - Added code-block copy affordance with `generated · not executed` labeling.
   - Added safe inline `\(...\)` and single-line/multiline `$$...$$` equation presentation.
   - Existing safe React headings/lists/tables, W# web citations, D# document citations and source cards remain intact; no `dangerouslySetInnerHTML`.
7. Added/expanded regression and acceptance tests for code routing, secret rejection, provider-call privacy boundary, safe public URLs, OpenAI source normalization, and I9 mutation planning.

## Provider SDK verification

Verified against current official documentation on 2026-09-09:
- OpenAI Responses API supports the hosted `web_search` tool and `web_search_call.action.sources` source metadata.
- Google Gen AI SDK supports `types.Tool(google_search=types.GoogleSearch())` with `GenerateContentConfig`.
The patch keeps those provider-hosted searches read-only and normalizes source metadata before exposing it to Ask LifeOS.

## Validation performed in this environment

PASS:
- `python -m compileall -q backend/ai backend/services backend/tests`
- `npm run css:check` -> CSS contract OK
- TypeScript `transpileModule` syntax check for `AskLifeOSPage.tsx` using global TypeScript 5.8.3
- Dependency-free capability smoke: exact calculator, code-request routing, secret rejection, safe public URL rejection
- OpenAI web source normalization smoke
- Security scan: no `dangerouslySetInnerHTML`; no Python `eval(...)`/`exec(...)` builtins in source
- New capability/reasoning/web/calculator/RAG/verifier services contain no direct DB session writes
- No Alembic migration added; latest expected revision remains `20260906_0001`

NOT FULLY RUN HERE (environment blockers, not marked as passes):
- `python -m pytest -q` stops while importing test `conftest.py` because the sandbox Python environment does not have Flask installed.
- `npm ci` could not populate dependencies because this sandbox cannot reach the npm registry.
- Consequently `npm run build` reports missing React/Babel/ESTree type-definition packages rather than a demonstrated source-code TypeScript regression.

## Required validation on your normal LifeOS machine

Run from the project after overlaying this ZIP:

```powershell
cd backend
py -3.11 -m pytest -q

cd ..\frontend
npm ci
npm run build
npm run css:check
```

Do not deploy this patch as fully validated until those dependency-backed commands pass in the normal project environment.

## Files in this cumulative patch

- `backend/.env.example`
- `backend/ai/model_router.py`
- `backend/ai/provider_router.py`
- `backend/ai/providers/base.py`
- `backend/ai/providers/gemini.py`
- `backend/ai/providers/openai_provider.py`
- `backend/services/agent_langgraph_runtime_service.py`
- `backend/services/agent_planner_service.py`
- `backend/services/agent_runtime_service.py`
- `backend/services/intelligence_ask_service.py`
- `backend/services/intelligence_capability_router_service.py`
- `backend/services/intelligence_claim_verifier_service.py`
- `backend/services/intelligence_rag_tool_service.py`
- `backend/services/intelligence_reasoning_service.py`
- `backend/services/intelligence_tool_registry_service.py`
- `backend/services/safe_calculator_service.py`
- `backend/services/web_research_service.py`
- `backend/tests/test_agent_provider_budget_general_intelligence.py`
- `backend/tests/test_ask_lifeos_general_capabilities_unit.py`
- `backend/tests/test_ask_lifeos_reasoning_i9_upgrade.py`
- `backend/tests/test_intelligence_tool_registry_i1.py`
- `backend/tests/test_provider_web_research_sources_unit.py`
- `frontend/src/pages/AskLifeOSPage.tsx`
- `frontend/src/styles/ux-refresh.css`
- `PATCH_MANIFEST_GENERAL_INTELLIGENCE_UPDATED.md`

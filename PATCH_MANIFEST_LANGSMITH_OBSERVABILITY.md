# LifeOS LangSmith Observability Patch

Baseline: the full project ZIP supplied immediately before this patch.

## What this patch does

- Keeps the LifeOS `AIUsageEvent` ledger authoritative for token/cost accounting.
- Adds metadata-only LangSmith operation traces for:
  - Document analysis
  - Document type detection
  - Document questions
  - Ask LifeOS / I19 entry point
  - Academic schedule import
- Adds child retriever spans for:
  - Document hybrid retrieval
  - Collection retrieval
  - Project-document retrieval
- Adds metadata-only LangSmith spans for Gemini generation and embeddings.
- Persists LangSmith embedding run IDs into the existing AI usage ledger.
- Adds LangSmith runtime configuration status to Analytics -> AI Usage (Development).
- Does not log raw prompts, uploaded document text, user questions, or generated answers.
- Does not change Gemini prompts/models/thinking, RAG ranking, I9 confirmation, or database mutation rules.
- No Alembic migration is required.

## Configure locally

In `backend/.env`:

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_key_here
LANGSMITH_PROJECT=lifeos-development
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_WORKSPACE_ID=
LANGSMITH_TRACING_SAMPLING_RATE=1.0
```

Do not commit the API key.

If tracing is disabled or misconfigured, LifeOS continues normally and the internal AI usage ledger still works.

## Install/update dependencies

```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\backend
py -3.11 -m pip install -r requirements.txt
```

`langsmith` was already present in the supplied project's requirements.

## Verify

Backend:

```powershell
py -3.11 -m pytest tests\test_langsmith_observability.py -q
py -3.11 -m pytest tests\test_ai_usage_observability.py -q
py -3.11 -m pytest -q
```

Frontend:

```powershell
cd ..\frontend
npm run build
npm run css:check
```

Then run one Document Analyze or Ask LifeOS request and open:

`Analytics -> AI Usage (Development)`

The LangSmith panel should show `Configured` when tracing, SDK, and API-key configuration are present. In LangSmith, the project should show a LifeOS operation trace with nested LLM/retriever/embedding spans where applicable.

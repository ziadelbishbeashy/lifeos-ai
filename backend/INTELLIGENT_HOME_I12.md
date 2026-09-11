# I12 — Intelligent Home / Today

I12 turns the existing dashboard into the primary verified LifeOS attention surface. It does **not** create a second AI pipeline and it does not call Gemini. The Home packet is an aggregation of already-reviewed intelligence capabilities:

- I8 portfolio priority ranking for **Your Focus Today**
- I9 confirmation-gated action proposals directly from a focus item
- I10 **What Changed Today** recent activity
- I11 next-7-day deadlines, document-analysis attention, and **Study Next**

## API

`GET /api/v1/intelligence/home`

The response is authenticated, ownership-bounded, read-only, and includes `verified_from_state: true`. Product payloads intentionally omit internal tools, chunks, embeddings, prompts, and other RAG implementation details.

`GET /api/v1/intelligence/today` remains available for compatibility. Its priority payload now includes the reviewed I9 action options that Home may offer; creating a proposal still performs no workspace mutation until the user confirms it.

## Safety contract

Home may display a suggested action, but it never writes directly. The flow remains:

`verified priority -> action proposal -> explicit user confirmation -> deterministic LifeOS service -> activity/audit event`

Dismissal or merely opening Home changes no project, task, note, document, or analysis state.

## UI

The existing dashboard structure remains intact. I12 adds:

- a verified daily briefing and four compact state signals in the hero
- a ranked focus panel with confirmation-gated actions
- document review, study-next, and recent-change cards
- verified next-seven-day deadlines
- graceful fallback to the existing dashboard state if the intelligence endpoint is unavailable

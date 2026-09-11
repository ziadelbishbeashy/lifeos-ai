# I19 — Agentic Ask LifeOS Runtime

Status: **integrated into Ask LifeOS; backend runtime remains constrained and auditable**.

I19 is no longer a separate user-facing Agent module. The `/agent` frontend route redirects to `/ask`, and the navigation exposes one intelligence surface: **Ask LifeOS**.

## Product behavior

Ask LifeOS chooses the smallest trusted path automatically:

- simple workspace facts -> deterministic LifeOS services
- selected document/module/collection knowledge -> existing Document Brain / grounded RAG
- project reviews/priorities -> existing verified intelligence services
- clear multi-step goals -> I19 bounded goal plan inside the conversation

A complex request such as `Help me get this project ready for deployment` returns a read-only plan first. Nothing executes until the user starts the review from the Ask LifeOS conversation.

## Runtime contract

`goal -> constrained planner -> owner-validated read-only tools -> evidence catalog -> reasoning -> audited run -> optional I9 proposal`

The runtime never receives SQL, ORM models, arbitrary code, arbitrary URLs, filesystem access, or unrestricted tools.

### Planner
- Goal plus optional explicit LifeOS context.
- Context ownership is revalidated.
- Code selects only reviewed I1 registry tools.
- Planning does not execute tools and does not create a run record.

### Read-only execution
Supported scopes:
- All LifeOS
- Project
- Document
- Collection
- Module
- Lecture

Workspace/project tools reuse deterministic LifeOS intelligence. Knowledge scopes reuse the existing Ask LifeOS / Document Brain grounded pipeline.

### Run audit
`lifeos_agent_runs` remains the internal audit table and stores:
- goal + selected scope
- canonical plan
- per-tool trace/duration/failure
- bounded evidence
- verified/fallback answer
- tool/provider call counts
- limits

The table name is an internal implementation detail; the product calls these **goal reviews**.

### Safe actions
Goal-review output may surface action suggestions only from existing verified priorities. Preparing one creates an existing I9 `LifeOSActionProposal`. No Task/Note/Document state changes until the authenticated owner confirms that proposal.

### Limits
- 6 plan steps
- 6 read-only tool calls
- 2 provider calls
- 45 second runtime budget
- 24 evidence items
- 3 action suggestions
- 30 history records per request

## Product API
Ask LifeOS uses the Intelligence boundary:
- `POST /api/v1/intelligence/ask` — detects clear goal-shaped requests and returns a safe plan
- `POST /api/v1/intelligence/goal-plan`
- `POST /api/v1/intelligence/goal-runs`
- `GET /api/v1/intelligence/goal-runs`
- `GET /api/v1/intelligence/goal-runs/<id>`
- `POST /api/v1/intelligence/goal-runs/<id>/proposals`

The older `/api/v1/agent/*` endpoints remain compatibility aliases for now; they are not a separate frontend module. I9 confirmation/dismiss endpoints remain unchanged.

I18 Visual Automations remains **working but not product-final**; its UX can continue improving independently.

## I19.6-I19.10 — Ask LifeOS product integration

I19 remains a hidden backend capability of Ask LifeOS. Goal-shaped requests now return a decision-first review: an overall readiness status, the biggest verified blocker, a few secondary risks, up to three focus steps, consolidated safe actions, and collapsed evidence. Explicit project-review requests keep their existing deterministic review path, but the frontend shows only the top focus by default and moves the full finding/evidence list behind disclosure controls. No new mutation path was added; all suggested changes still cross I9 confirmation.


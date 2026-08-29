# LifeOS Intelligence Core V1 — I1 + I2 + I3

This phase builds the intelligence layer **above** Document Brain. It does not
replace RAG and it does not give an LLM database access.

## Reliability contract

- LLMs may reason; they do not query SQL directly.
- Every capability available to orchestration must be registered in the reviewed
  Tool Registry.
- The current registry is read-only.
- Unknown tools fail closed.
- Mutating tools require a future explicit action/confirmation boundary.
- Ownership is checked inside the called LifeOS service, not trusted from model
  output or user-supplied IDs.
- Product responses separate verified/calculated facts from inferences and
  suggestions.
- Low-confidence or ambiguous scope resolution asks for clarification instead of
  guessing.
- Internal tool names, retrieval ranks, chunk IDs and embeddings are not exposed
  by the user-facing intelligence API.

## I1 — Tool + Project Review foundation

1. `services/intelligence_tool_registry_service.py`
   - allow-listed structured tools
   - read-only risk metadata
   - strict arguments
   - fail-closed unknown/mutation behavior
2. `services/intelligence_planner_service.py`
   - deterministic `project_review` plan
3. `services/intelligence_executor_service.py`
   - executes reviewed plans with mutation disabled
4. `services/project_review_intelligence_service.py`
   - reviews task state + current document intelligence + recent notes
   - returns facts, signals and suggestions separately
   - performs no writes and no provider calls
5. `GET /api/v1/intelligence/projects/<project_id>/review`

## I2 — Trusted Context Engine V2

`services/intelligence_context_service.py` now builds an auditable context packet
containing:

- scope identity
- verified project state
- manual project progress **separate from** calculated task completion
- deterministic task counts / overdue / blocked / due-soon values
- current document count
- stale and unanalysed document-intelligence counts
- note count
- bounded recent activity derived only from already-authorized tool results
- source provenance + freshness on facts
- context-limit metadata

The public context endpoint deliberately omits raw `tool_data`:

`GET /api/v1/intelligence/projects/<project_id>/context`

## I3 — Intent + Scope Router

`services/intelligence_intent_router_service.py` introduces a deterministic first
router for these reviewed intent labels:

- `project_review`
- `project_question`
- `task_status`
- `recent_activity`
- `knowledge_search`
- `document_question`
- `module_question`
- `general_conversation`

Project scope is resolved only from projects already owned by the authenticated
user. Exact title matches win; ambiguous/low-confidence requests return a
clarification rather than silently choosing a project.

`services/intelligence_request_service.py` connects routing to reviewed
executors. At this checkpoint only `project_review` executes automatically; the
other recognized intents return `route_only` until their safe executors exist.

API:

`POST /api/v1/intelligence/route`

Example body:

```json
{"query": "How is my LifeOS project going?"}
```

CLI:

```powershell
python -m flask --app app intelligence-route --user-id 1 --query "How is my LifeOS project going?"
python -m flask --app app intelligence-project-context --user-id 1 --project-id 1
```

## Why the router is deterministic first

The first milestone proves that LifeOS can understand common requests and choose
an owned scope without letting an LLM invent database IDs or choose arbitrary
capabilities. The next reasoning layer receives a verified route + trusted
context instead of uncontrolled database access.

## Next slice

- I4 LLM reasoning over verified route/context/tool results
- I5 claim verifier for LLM-generated inferences
- natural Project Review narrative
- additional read-only executors for task status / recent activity / knowledge
  search
- then explicit Action Proposals (still no silent writes)

## I4 — Context-grounded Reasoner

`services/intelligence_reasoning_service.py` adds the first natural-language
reasoning layer. The provider receives only the reviewed project context packet
and product-level review signals; it has no direct SQL, ORM, or arbitrary tool
access. Factual prose must be emitted with explicit `{fact key, exact value}`
bindings, while inferences/recommendations must name their trusted support.

## I5 — Claim Verification

`services/intelligence_claim_verifier_service.py` verifies reasoning in two
stages:

1. deterministic checks make every factual binding match current LifeOS state
   and ensure inference/recommendation support references exist;
2. an independent provider pass rejects prose that adds unsupported or
   contradictory claims.

If reasoning or verification fails (including quota/network/provider failure),
LifeOS fails closed to a deterministic answer assembled from verified project
state. Unverified model prose is never returned as the product answer.

## Ask LifeOS V0

The first product-level endpoint is read-only and intentionally narrow:

`POST /api/v1/intelligence/ask`

with:

```json
{"query": "How is my LifeOS project going?"}
```

Only the verified `project_review` workflow executes today. Other recognized
intents remain route-only until they receive their own reviewed tools and
verification contract.

CLI smoke test:

```bash
python -m flask --app app intelligence-ask --user-id 1 --query "How is my LifeOS project going?"
```

A successful AI response reports `response_mode=ai_verified`. If the provider
or verifier is unavailable, `response_mode=deterministic_fallback` is expected
and still uses trusted LifeOS state.

## I8 — Constrained Project Review Agent

The first read-only agentic workflow is now built on the trusted context layer.
It separates status review from prioritization:

- `project_review` answers how one project is going.
- `portfolio_review` summarizes all projects.
- `project_focus` ranks what deserves attention inside one project.
- `portfolio_focus` ranks attention across owned projects.

The I8 agent reuses existing allow-listed tools/context, ranks evidence-backed
priorities deterministically, exposes no direct database/model control, and
performs no mutations. See `I8_PROJECT_REVIEW_AGENT.md`.

## I9 — Safe Action + Confirmation Engine

I9 introduces the first write boundary without giving AI or retrieved content
write authority.  I8 priorities expose a reviewed action allow-list. Clicking
an action creates a `lifeos_action_proposals` row in `pending` state; it does
**not** change Tasks, Notes, Documents, or Projects. Only a second authenticated
confirmation can execute the action through existing deterministic services.

Initial actions:

- create a project Task
- save a project Note
- refresh the current analysis for an owned Document

The state machine is `pending -> executing -> confirmed|failed` (or `dismissed`).
The `executing` transition is committed before execution so duplicate confirm
requests cannot run the same proposal twice. Confirmed actions retain an audit
record and feed I10 activity history.

API:

- `POST /api/v1/intelligence/action-proposals`
- `GET /api/v1/intelligence/action-proposals/<id>`
- `POST /api/v1/intelligence/action-proposals/<id>/confirm`
- `POST /api/v1/intelligence/action-proposals/<id>/dismiss`

## I10 — Recent Activity / What Changed?

I10 adds `lifeos_activity_events`: small structured records of meaningful
workspace changes. Project/Task/Note mutations, document-version activation,
document analysis, and confirmed LifeOS actions append auditable events. Raw
note/document content, prompts, API keys, and retrieval internals are not stored
in activity summaries.

Ask LifeOS now executes the `recent_activity` intent deterministically:

- `What changed recently?`
- `What changed in LifeOS this week?`
- `What changed across all my projects this week?`

For records that pre-date I10, the service derives bounded recent events from
trusted timestamps (project/task/note/document/analysis state), so the feature
is useful immediately after migration. Logged events take precedence as new
changes occur.

CLI:

```bash
python -m flask --app app intelligence-activity --user-id 1 --query "What changed this week?"
```

Direct API:

`GET /api/v1/intelligence/activity?q=What%20changed%20this%20week%3F`

Migration head after I9/I10: `20260829_0001`.

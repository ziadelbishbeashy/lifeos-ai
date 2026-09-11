# I18 — Visual Flow Builder (I18.1–I18.6)

I18 is a visual orchestration layer on top of the existing I17 intelligence automation engine. It is **not** a generic n8n clone and it does not introduce a second automation runtime.

## Trust and execution boundaries

- React owns canvas/UI only.
- The backend canonicalizes every graph and compiles it to allow-listed LifeOS capabilities.
- I17 remains responsible for run audit, Run now, Preview, schedule/event candidate selection, worker execution, automation status, and I14/I15 notification delivery.
- Visual nodes never receive direct SQL/model/arbitrary-code/arbitrary-URL access.
- Structured workspace facts come from approved application services.
- Document/Collection/Module knowledge continues through the existing authoritative Document Brain/RAG paths.
- Important workspace mutations still require the existing I9 confirmation boundary.
- Proposal nodes can create only a pending I9 proposal; they never execute the proposed workspace mutation.
- Preview is dry-run and never persists an I9 proposal.

## Implemented phases

### I18.1 — Canvas and canonical graph

- Drag/drop visual canvas
- Node registry
- Connections and layout persistence
- Save/load canonical graph
- Backend ownership validation
- No cycles, branching, merging, dangling nodes, or unknown capabilities

### I18.2 — Constrained compiler

- Backend graph → deterministic execution plan
- Approved service-boundary metadata per node
- Storage compatibility with I17 trigger/action columns
- Stable plan fingerprint
- Backend compile endpoint

### I18.3 — Run now / Preview

Rich compiled flows execute step-by-step through approved LifeOS services. Exact legacy-compatible three-node flows still use the original I17 direct execution path.

### I18.4 — Background visual workflows

Schedule and I14-event compiled flows are eligible for the existing I17 worker. Manual trigger flows are explicitly owner-run only and cannot be enabled for background execution.

### I18.5 — Run diagnostics

- Node-level status trace
- Service-boundary trace
- Node duration
- Failed node id and error evidence
- Partial trace preserved on failure
- Clear visible automation error without deleting run history

All diagnostics are stored inside the existing `lifeos_automation_runs.output_json`; no schema change is required.

### I18.6 — UX and templates

- Visual starter templates
- Manual Run trigger
- Run history/debugging UI
- Node trace status UI
- Clear Error control
- Updated live capability labels and execution states

## Compiled execution model

```text
Visual Canvas
    ↓
Backend canonical graph
    ↓
Constrained compiler
    ↓
Approved execution plan
    ↓
I17 executor / worker
    ↓
Approved LifeOS services
    ↓
Verified result + run audit
    ↓
I14/I15 notification (when requested)
    ↓
I9 proposal/confirmation if an important workspace action is suggested
```

## Safety invariants

The following remain false for visual flow nodes:

- arbitrary code execution
- arbitrary SQL execution
- arbitrary URLs
- direct model/provider access
- direct workspace mutation
- LLM direct DB writes

I9 remains mandatory for create-task/save-note/refresh-analysis proposals.

## Migration

I18.3–I18.6 require no new tables or columns. The existing additive visual metadata migration is sufficient, so the migration head remains:

`20260830_0002`

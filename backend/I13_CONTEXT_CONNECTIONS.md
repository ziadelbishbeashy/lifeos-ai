# I13 — Context Connections

I13 makes LifeOS resources explicitly traceable without creating a second knowledge or AI pipeline.

## Contract

- Existing Project, Module/Lecture and Collection relationships remain authoritative.
- `lifeos_context_links` stores only relationships that do not already have a natural domain table, especially provenance created after a confirmed Ask LifeOS action.
- Both endpoints of every persisted or returned edge are re-validated against the authenticated owner.
- AI/retrieved text is never authorization to create a connection.
- Confirmed I9 task/note actions preserve their source document evidence as `derived_from` edges.
- Pre-I13 confirmed I9 actions remain traceable through a read-only compatibility view, so old work does not lose provenance.
- Connection queries are deterministic and read-only.

## Ask LifeOS examples

- `Why does task #84 exist?`
- `Which document is task #84 based on?`
- `Which tasks came from Deployment_Plan.pdf?`
- `What is connected to Architecture.pdf?`
- `Show connections for note #12`

## API

`GET /api/v1/intelligence/connections/<resource_type>/<resource_id>`

Supported resources: project, task, note, document, module, lecture, collection, document_analysis.

## Migration

`20260829_0002` adds `lifeos_context_links`. No existing column is altered.

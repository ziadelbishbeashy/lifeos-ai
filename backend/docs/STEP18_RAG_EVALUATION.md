# Step 18 — RAG Evaluation

Step 18 adds an objective regression harness around the **existing** LifeOS
Document Brain retrieval and grounded-answer workflows. It does not create a
second retrieval stack and it does not change user-facing answer behavior.

## What it measures

A gold JSON case can declare:

- the owned scope to query: `document`, `project`, `collection`, `module`, or
  `lecture`;
- the exact question;
- expected answerability (`true` / `false`);
- deterministic answer facts that must appear or must not appear;
- expected retrieval evidence by filename/document ID, page, section, and/or
  `content_type` (`text` or `table`);
- expected answer citations.

The report includes:

- retrieval source recall;
- retrieval all-required-sources rate;
- reciprocal rank / MRR;
- answerability accuracy;
- deterministic answer-text accuracy;
- citation source recall;
- citation all-required-sources rate;
- per-case evidence and failure details.

This is intentionally a **regression evaluator**, not an LLM-as-judge system.
Gold facts and source selectors stay explicit so a model change cannot silently
move the scoring target.

## Authoritative-path rule

The evaluator calls the same production services used by LifeOS:

- single document -> `retrieve_owned_document_chunks_hybrid`;
- project -> `retrieve_owned_project_document_chunks`;
- collection -> `retrieve_owned_collection_chunks`;
- module/lecture -> the exact Module document-scope resolver +
  `retrieve_owned_document_set`;
- full answer mode -> the existing Document / Project / Collection / Module
  question workflows with `force=True`.

Full mode removes the evaluation-created question-history row after scoring so
running the benchmark does not fill the user's normal Q&A history. Chunk and
embedding caches are intentionally preserved.

## Included Northstar gold set

`evaluations/northstar_step18.json` contains the current Northstar regression
cases for:

- Laptop Q4 units = `3,250`;
- highest return rate = `Headphones — 6.4%`;
- below reorder point = `Laptops` and `Smartwatches`;
- collection codename/manager/budget = `AURORA-26`, `Nadia Fawzy`,
  `EGP 8.4 million`;
- three-document answer = `16 November 2026`, `EGP 8.4 million`,
  `Accessories — 8,600` for the broad "product" wording;
- unsupported CEO salary -> no grounded answer.

The collection cases resolve an owned collection by the three exact Northstar
filenames, so the collection itself does not need a hard-coded name. If your
local filenames differ, edit only the dataset selectors; do not change RAG code
just to satisfy the benchmark.

## Commands

Run from `backend/`.

### Retrieval baseline

This measures hybrid retrieval/source placement without running answer
generation/answerability calls:

```powershell
python -m flask --app app rag-eval `
  --dataset evaluations/northstar_step18.json `
  --user-id 1 `
  --mode retrieval `
  --output reports/northstar-retrieval.json
```

Hybrid retrieval can still use the configured embedding provider. If semantic
embeddings are unavailable, the production keyword-fallback behavior is what is
evaluated.

### Full grounded RAG baseline

This also runs the real answerability verifier and grounded answer workflow:

```powershell
python -m flask --app app rag-eval `
  --dataset evaluations/northstar_step18.json `
  --user-id 1 `
  --mode full `
  --output reports/northstar-full.json
```

`full` mode can consume configured AI-provider quota. It should be run
intentionally, not from unit tests.

### CI / release gate

The command exits non-zero when a case fails, errors, or a configured threshold
is missed. Use `--no-fail` only when collecting a diagnostic report without
blocking the current shell/CI step.

## Dataset schema (v1)

```json
{
  "version": 1,
  "name": "Example",
  "defaults": {"top_k": 10},
  "thresholds": {
    "retrieval_recall": 0.9,
    "answerability_accuracy": 1.0,
    "citation_recall": 0.9
  },
  "cases": [
    {
      "id": "example_case",
      "tags": ["table"],
      "scope": {
        "type": "document",
        "filename": "example.pdf"
      },
      "question": "What was Q4 sales?",
      "expected": {
        "answerable": true,
        "answer_contains": ["3,250"],
        "answer_not_contains": ["4,000"],
        "sources": [
          {
            "filename": "example.pdf",
            "page": 3,
            "content_type": "table"
          }
        ]
      }
    }
  ]
}
```

Use `retrieval_sources` and `citation_sources` instead of `sources` when the
expected retrieval evidence and final citations intentionally differ.

## Step 18 release gate

Do not mark Step 18 as proven on the real LifeOS database until:

1. `python -m pytest tests -q` passes in the project environment;
2. the Northstar retrieval evaluation passes;
3. the Northstar full evaluation passes with the configured provider;
4. the generated JSON report is saved as the baseline for future changes;
5. a deliberate retrieval/grounding regression makes the command fail (proves
   the gate is capable of catching a bad change).

There is no Step 18 database migration and no frontend redesign. The expected
migration head remains the Modules V1 head (`20260828_0004`) until a later
feature genuinely changes persistence.

## Gold citation calibration

The Northstar gold set scores the source page that directly supports each fact.
For the Retail fixture, Laptop Q4 units are cited from page 3, highest return
rate from page 5, and below-reorder-point categories from page 6. A correct
answer should not fail merely because a different valid supporting table page
was originally hard-coded in the gold set.

A provider usage/rate-limit exception in `--mode full` is reported as an
execution error, not a RAG-quality failure. Wait for the provider window to
reset and rerun the full evaluation; do not lower quality thresholds to hide a
provider quota error.


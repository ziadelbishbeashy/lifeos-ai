# Step 18 — RAG Evaluation

Implementation and usage details are in:

`docs/STEP18_RAG_EVALUATION.md`

Quick start from `backend/`:

```powershell
python -m flask --app app rag-eval --dataset evaluations/northstar_step18.json --user-id 1 --mode retrieval --output reports/northstar-retrieval.json
python -m flask --app app rag-eval --dataset evaluations/northstar_step18.json --user-id 1 --mode full --output reports/northstar-full.json
```

Step 18 reuses the existing Document / Project / Collection / Module RAG paths.
It adds a gold regression harness, not a second RAG implementation.

## Gold-source calibration note
For structured-table cases, retrieval ranking and final citation provenance are deliberately scored separately:
- `retrieval_sources` checks that the correct source page is ranked highly, whether the retriever returns its native/flattened text chunk or the dedicated table chunk first.
- `citation_sources` remains strict and can require `content_type: "table"` so full-mode evaluation still proves that structured table evidence survives into grounded answers.

This avoids penalizing a correct page-level retrieval solely because the native-text representation of the same page ranks immediately above its table-aware representation.

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


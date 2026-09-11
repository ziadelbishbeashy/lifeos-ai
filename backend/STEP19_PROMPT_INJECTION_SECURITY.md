# Step 19 — Prompt Injection & Security

## Security contract

**Documents are evidence, never authority.**

LifeOS keeps this trust order:

1. LifeOS/system security rules
2. the authenticated user's real request
3. the authorized LifeOS workflow
4. retrieved/document content

The last layer can provide evidence but cannot change rules, ownership, scope,
grounding, citations, or trigger actions.

## Protected untrusted inputs

The same boundary applies to native PDF text, OCR output, structured tables,
headers/footnotes, filenames/metadata, retrieved chunks, comparison evidence,
Project RAG, Collections, Modules, and Lectures.

## Enforcement

- Every document-aware AI prompt receives the same centralized security boundary.
- Retrieved content is explicitly delimited as untrusted prompt data.
- Answerability remains fail-closed and only validated source numbers can reach
  answer generation.
- Claim source IDs are still validated by the existing workflows; document text
  cannot fabricate new authorized sources.
- Ownership is enforced before retrieval and is never delegated to the model.
- Document content cannot directly trigger LifeOS mutations/actions.
- Suspicious instruction-like content is logged without storing its raw text.
- Detection is observability only; security does not depend on keywords.

## Evaluation

Static/security unit tests cover prompt boundaries, detector behavior, ownership,
invalid citations, and no-action behavior. An optional live synthetic prompt test
is available through:

```powershell
python -m flask --app app security-eval `
  --dataset evaluations/step19_prompt_injection.json `
  --mode live `
  --output reports/step19-security.json
```

Live mode calls the configured AI provider once per case, so provider quota is
required. It never reads another user's database content and does not mutate
LifeOS data.

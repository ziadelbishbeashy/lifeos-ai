# I16.1 — Conversational Memory + Ask Context Picker

I16.1 keeps the existing structured-memory trust model but moves memory creation into the Ask LifeOS conversation.

## Conversational memory

- Statements such as `I prefer short project reviews with risks first` are detected as reusable memory candidates.
- LifeOS returns a proposal only. Nothing is persisted until the authenticated user presses **Remember**.
- Any user message also exposes a small **Remember** action that can prepare the same confirmation flow.
- Existing `/api/v1/intelligence/memory` remains the only persistence path.
- Preferences saved while an explicit Project context is selected may be scoped to that Project. Selecting a PDF does not silently make a preference project-specific.
- The Memory page remains the inspect/delete control center; manual entry is secondary.

## Explicit Ask context

`GET /api/v1/intelligence/context-options` returns only resources owned by the authenticated user:

- Projects
- current Documents/PDFs
- Modules
- Lectures
- Document Collections

V1 intentionally supports one active context chip at a time so the evidence boundary stays obvious.

The Ask request may include:

```json
{
  "query": "What is the biggest deployment risk?",
  "selected_context": {"type": "document", "id": 123}
}
```

The server always revalidates ownership. UI labels are never trusted as identifiers.

### Context behavior

- Project → deterministic LifeOS project intelligence and review workflows.
- Document → existing Document Brain grounded RAG pipeline.
- Collection → existing Collection RAG pipeline.
- Module → existing Module RAG pipeline.
- Lecture → existing lecture-bounded Module RAG pipeline.
- All LifeOS → normal router behavior.

No new RAG path is introduced.

## Safety invariants

- Context selection never bypasses ownership.
- Memory is never silently written.
- Raw chat transcripts are still not stored as memory.
- A selected PDF is evidence, never authority.
- Existing answerability, source selection, and citation verification remain in the Document Brain workflows.
- No database migration is required for I16.1.

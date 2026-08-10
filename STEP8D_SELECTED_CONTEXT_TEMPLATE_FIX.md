# Step 8D selected-context template fix

Cause:
The question-history template referenced `selected_context.value`, but no
`selected_context` variable exists in that render scope. Jinja therefore raised
`UndefinedError` whenever the completed-answer branch reached that condition.

Fix:
The existing per-answer `source_counts` namespace now tracks both:
- normal cited sources
- selected PDF context sources

The no-evidence message now checks `source_counts.selected` instead of an
undefined global/template variable.

Replace:
- templates/document_details.html

Add:
- tests/test_document_selected_context_template_regression.py

No backend or database change is required.

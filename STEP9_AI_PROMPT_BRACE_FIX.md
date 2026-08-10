# Step 9 AI prompt brace fix

## Root cause

Step 9 added `tags` to the example `action_items` object inside
`_build_document_analysis_prompt()`.

That prompt is an f-string. The outer JSON example already escaped most braces
as `{{` and `}}`, but the new action-item object and its nested source object
were accidentally left as ordinary `{` and `}`.

Python therefore tried to interpret the JSON body as an f-string expression /
format specifier and raised:

    ValueError: Invalid format specifier ...

This single prompt-construction error caused all seven document-analysis tests
to fail before any AI provider call occurred.

## Fix

Escaped the braces for:
- the example action-item object
- the nested source object

No behavior, model, database, route, or migration changes are required.

Replace:
- services/ai_service.py

Add:
- tests/test_step9_document_analysis_prompt_regression.py

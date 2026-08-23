# Step 14 Route Test Mock Fix

The production `CreatedDocumentVersion` contract includes `upload_result`.

The failing route test mocked `create_new_document_version()` with a
`SimpleNamespace` that omitted that field, while the route legitimately reads:

- `result.upload_result.extraction_succeeded`
- `result.upload_result.pages_with_text`

This patch fixes the TEST DOUBLE, not production code, by adding:

```python
upload_result=SimpleNamespace(
    extraction_succeeded=True,
    pages_with_text=1,
),
```

Replace only:

`tests/test_document_version_routes_step14.py`

Then run:

```powershell
python -m pytest tests\test_document_version_routes_step14.py -v
python -m pytest
```

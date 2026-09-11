# Apply Step 15E.1 — OpenCV OCR preprocessing

This patch is backend-only. It does not redesign the frontend.

1. Copy the patch over the current LifeOS project.
2. Install the new dependency:

```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\backend
python -m pip install -r requirements.txt
```

3. Add to `backend\.env`:

```env
OCR_PREPROCESSING_ENABLED=true
OCR_PREPROCESSING_MODE=auto
```

4. Run the focused tests:

```powershell
python -m pytest tests\test_ocr_preprocessing_step15e.py tests\test_document_ocr_service_step15.py -v
```

5. Restart Flask and retry OCR on a scanned PDF.

Use `OCR_PREPROCESSING_MODE=document` only when testing a difficult scan where
`auto` still produces weak OCR.

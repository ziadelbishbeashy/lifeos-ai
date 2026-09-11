# LifeOS backend update bundle — 2026-08-26

This backend folder is based on the user's latest `lifeos-ai-feature-hybrid-rag (6)` backend and includes the backend work added afterward:

- Step 15 OCR foundation and OCR API/workflow/state migration
- Tesseract OCR provider and PDF page rendering
- Existing RAG/chunk pipeline reuse after OCR
- Step 15E.1 OpenCV OCR preprocessing (`none`, `auto`, `document` modes)
- Modern `pymupdf` import path
- Same-origin inline PDF viewer header fix for `/api/v1/documents/<id>/file`
- OCR/preprocessing regression tests plus an inline-PDF API regression test

## Important

Do **not** delete your real `backend/.env` when replacing the folder. This bundle intentionally contains `.env.example`, not your secrets.

Recommended OCR settings in your existing `.env`:

```env
OCR_PROVIDER=tesseract
OCR_TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
OCR_LANGUAGES=eng
OCR_RENDER_DPI=300
OCR_LOW_CONFIDENCE_THRESHOLD=0.70
OCR_AUTO_ENQUEUE=false
OCR_PREPROCESSING_ENABLED=true
OCR_PREPROCESSING_MODE=auto
```

After copying the backend folder, run:

```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\backend
python -m pip install -r requirements.txt
python -m flask --app app db upgrade
python app.py
```

Current OCR migration head should be `20260826_0001`.

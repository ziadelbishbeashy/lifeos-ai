# LifeOS Step 15G — Adaptive OCR

This backend pass adds a page-level OCR quality engine without changing the frontend or RAG architecture.

## New recognition flow

1. Native PDF text is kept when it is genuinely useful.
2. Scanned/thin-text-over-image pages are rendered and preprocessed with OpenCV.
3. Tesseract tries configured PSM strategies in order (`3,6,11` by default).
4. If a Tesseract pass becomes `acceptable` or `good`, later Tesseract passes are skipped.
5. If the best Tesseract result is still `poor` and EasyOCR fallback is enabled, EasyOCR runs for that page.
6. LifeOS compares the candidates and keeps the stronger result.
7. The chosen result, confidence, provider, strategy, word boxes, and attempt audit are persisted in OCR layout JSON.
8. Existing chunking, embeddings, hybrid retrieval, Ask AI, Verify, and PDF selectable-text behavior remain authoritative.

## Install EasyOCR on Windows

EasyOCR is optional and intentionally kept out of the core `requirements.txt` because it pulls PyTorch.

First install PyTorch/torchvision appropriate for your Windows machine. For CPU-only usage, use the CPU option from PyTorch's official "Start Locally" page.

Then:

```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\backend
python -m pip install -r requirements-easyocr.txt
```

The first EasyOCR fallback may download model files. Keep `OCR_EASYOCR_DOWNLOAD_ENABLED=true` for the initial setup unless you pre-seed the model directory.

## `.env`

Keep the existing Tesseract/OpenCV settings and add:

```env
OCR_TESSERACT_PSM_MODES=3,6,11
OCR_EASYOCR_ENABLED=true
OCR_EASYOCR_LANGUAGES=en
OCR_EASYOCR_GPU=false
OCR_EASYOCR_DOWNLOAD_ENABLED=true
```

For Arabic + English:

```env
OCR_LANGUAGES=eng+ara
OCR_EASYOCR_LANGUAGES=en,ar
```

No database migration is required for Step 15G.

## Test

```powershell
python -m pytest tests -k "ocr" -v
```

The new tests are:

- `tests/test_ocr_adaptive_step15g.py`
- `tests/test_ocr_provider_config_step15g.py`

They do not call live OCR/AI providers.

## Manual benchmark: document 1010

Re-run OCR on the Lagrange PDF. In backend logs, each OCR page now includes:

- `selected_provider`
- `selected_strategy`
- `provider_attempts`
- character/word count
- confidence
- quality

For the current poor pages, expect Tesseract PSM attempts and then EasyOCR fallback when all Tesseract attempts remain poor.

After OCR completes, ask a NEW question (or force a question refresh) and look for non-zero keyword matches for terms that visibly exist in the PDF.

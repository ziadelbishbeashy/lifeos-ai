# Apply Step 15 OCR

This package is based on the uploaded `lifeos-ai-feature-hybrid-rag (6).zip`.
Frontend layout/CSS was intentionally left untouched.

## 1. Install backend Python dependencies

```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\backend
python -m pip install -r requirements.txt
```

## 2. Install Tesseract on Windows

Install Tesseract 5.x and the language packs you need. Then set in `backend/.env`:

```env
OCR_PROVIDER=tesseract
OCR_LANGUAGES=eng
OCR_TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
OCR_RENDER_DPI=300
OCR_LOW_CONFIDENCE_THRESHOLD=0.70
OCR_AUTO_ENQUEUE=false
```

For Arabic too, install the Arabic language data and use `eng+ara`.

## 3. Apply the database migration

```powershell
python -m flask --app app db upgrade
python -m flask --app app db current
```

The current revision should be `20260826_0001`.

## 4. Run the OCR-specific tests first

```powershell
python -m pytest tests\test_document_ocr_service_step15.py tests\test_document_ocr_workflow_step15.py tests\test_api_v1_document_ocr_step15.py tests\test_document_ocr_migration_step15.py -v
```

## 5. Run the full release gate

```powershell
cd ..
.\scripts\check-react-parity.ps1
```

## 6. Functional local test

Upload a scanned PDF. Its JSON document state should report `ocr.status=pending`.
Start OCR through:

```http
POST /api/v1/documents/{id}/ocr
```

With `JOB_BACKEND=inline` the development request performs OCR immediately. After
it completes, `GET /api/v1/documents/{id}/ocr` should report `completed`, and the
existing Document Brain search/Ask AI pipeline should be able to retrieve the OCR
text using the original PDF page numbers.

# Step 15E.1 — OCR Image Quality Pipeline

LifeOS already performs page-aware OCR fallback. This step adds a provider-neutral
OpenCV cleanup stage **before** Tesseract (and future OCR providers).

## Why it exists

OCR engines recognize text; OpenCV improves the pixels they receive.

```
PDF page
  -> render PNG
  -> OpenCV preprocessing (optional)
  -> Tesseract / future EasyOCR
  -> page-aware text
  -> existing chunking + Hybrid RAG
```

## Modes

- `none`: no pixel changes.
- `auto`: grayscale, low-contrast enhancement when needed, and conservative deskew.
- `document`: `auto` plus Otsu black/white thresholding for difficult paperwork scans.

`auto` is the recommended starting mode. `document` is intentionally more
aggressive and should be tested on the user's real documents before becoming a
default.

## Configuration

```env
OCR_PREPROCESSING_ENABLED=true
OCR_PREPROCESSING_MODE=auto
```

The feature can be switched off without changing the OCR provider or RAG
pipeline.

## Important boundary

OpenCV does not understand text. It only prepares the image. Tesseract/EasyOCR
perform recognition, and LifeOS RAG consumes the recognized text.

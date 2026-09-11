# LifeOS PDF selection + OCR text layer fix

This patch fixes two integrations without redesigning Document Brain:

1. **Select text → Ask about this** now crosses the PDF.js/React boundary through a React-safe custom event instead of trying to write into Ask-tab DOM that is not mounted yet.
2. **Scanned PDFs become selectable after OCR**. Tesseract word bounding boxes are stored as normalized page layout and the PDF viewer uses them as an invisible selectable OCR text layer whenever the PDF has no useful native text layer.

## Apply

Copy the `backend` and `frontend` folders from this patch over the matching folders in your LifeOS project.

Then run:

```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\backend
python -m flask --app app db upgrade
python -m flask --app app db current
```

Expected migration head:

```text
20260826_0002 (head)
```

Restart backend and frontend.

## Important for OCR documents processed before this patch

Older completed OCR jobs do not yet have word-position layout saved. The document page will show **Build OCR text layer**. Click it once. LifeOS will re-run OCR with `force=true` and persist the selectable word positions.

After that:

- Open the PDF workspace.
- On a scanned page, drag over OCR text in the PDF.
- The floating **Ask about this** button should appear.
- Clicking it closes the PDF viewer, opens the Ask AI tab, and shows the selected passage + page as grounded context.

Native-text PDFs continue using PDF.js's own text layer; OCR is only used as the fallback.

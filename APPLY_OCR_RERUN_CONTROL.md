# OCR re-run control

This patch changes only `frontend/src/pages/DocumentDetailsPage.tsx`.

After a document has completed OCR, the button now shows **Re-run OCR** instead of a disabled **OCR complete** state. Clicking it sends `force: true` to the existing OCR endpoint so the document is processed again using the current OCR/OpenCV settings.

Apply by copying the `frontend` folder over the project root, then restart Vite and hard-refresh the browser.

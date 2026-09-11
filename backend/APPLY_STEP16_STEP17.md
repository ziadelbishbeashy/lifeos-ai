# Apply LifeOS Steps 16 & 17

1. Back up your current project first.
2. Replace only the `backend` and `frontend` folders with the folders from this package.
3. Keep your existing local `backend/.env`. Do not replace it with `.env.example`.

## Backend

In PowerShell:

```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\backend
python -m pip install -r requirements.txt
python -m flask --app app db upgrade
python -m flask --app app db current
```

Expected migration head:

```text
20260828_0002 (head)
```

Run the focused regression gate:

```powershell
python -m pytest tests -k "table or collection or ocr" -v
```

Then run the full backend suite:

```powershell
python -m pytest tests -q
```

Start backend:

```powershell
python app.py
```

## Frontend

Open a second PowerShell window:

```powershell
cd C:\Users\zelbi\OneDrive\Desktop\lifeos-ai\frontend
npm install
npm run build
npm run dev
```

Do not use `npm audit fix --force` merely to remove development-tool audit warnings.

## Quick acceptance test

Tables:
1. Open an existing readable PDF that visibly contains a table.
2. Open **Tables**.
3. Press **Re-scan tables** once for older PDFs.
4. Confirm rows/columns appear correctly.
5. Ask a question whose answer depends on one cell/row relationship.

Collections:
1. Document Brain -> **Collections**.
2. Create a collection.
3. Add two readable PDFs.
4. Ask a question that can be answered from either/both files.
5. Open the returned source document and confirm the cited page/evidence.

OCR was not changed by Steps 16/17.

# LifeOS Document Brain — Step 6C

This patch connects Step 6B type detection to the Document Brain UI.

New user flow:
1. Open a readable PDF.
2. Click Detect document type.
3. LifeOS performs only the lightweight classifier request.
4. The page shows the detected type, confidence, and a short reason.
5. The user can keep the detected type or select another supported type.
6. Confirm and analyse submits the selected `confirmed_document_type`.

Important:
- This step creates the confirmation experience and route wiring.
- Step 6D is the next step that makes the full AI analysis prompt consume
  `confirmed_document_type` and return type-specific fields.
- No database migration is required.
- Type detection itself is not stored as a completed analysis.

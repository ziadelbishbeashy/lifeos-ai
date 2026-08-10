# LifeOS Document Brain — Step 6D

Step 6D connects the confirmed document type to the full analysis.

Production flow after this patch:

1. Detect document type.
2. Show detection to the user.
3. User confirms or changes the type.
4. POST /documents/<id>/analyse includes the detected and confirmed type.
5. The backend selects the confirmed Step 6A profile.
6. Gemini receives a prompt specialized for that exact document type.
7. The backend validates the response against that profile.
8. Unknown type-specific fields are discarded.
9. The saved insights JSON includes:
   - document_type_key
   - document_type
   - type_specific
   - type_metadata
10. The source fingerprint includes the confirmed type, so an analysis
    produced as Research Paper cannot be reused as Meeting Notes.

Important:
- The user-confirmed type wins.
- Gemini is not allowed to silently reclassify during full analysis.
- Common Step 5 sections remain for LifeOS integration.
- Type-specific sections are additive.
- No database migration is required.
- Step 6E will render these type-specific sections in the dashboard.

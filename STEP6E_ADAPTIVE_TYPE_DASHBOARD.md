# LifeOS Document Brain — Step 6E

Step 6E completes the adaptive document-type dashboard.

What changes:
- the saved confirmed type now changes what the user sees;
- the Overview tab shows a type-aware workspace summary;
- each profile's specialized sections are shown dynamically;
- only populated sections are expanded in Insights;
- source page/section/evidence remains attached to each specialized item;
- user overrides are visibly identified;
- legacy Step 5 analyses continue to render safely;
- empty specialized sections do not create fake content.

No database migration is required.

New file:
- services/document_type_workspace_service.py

Updated:
- routes/document_routes.py
- templates/document_details.html
- static/css/theme-v2.css

Tests:
- tests/test_document_type_workspace_service.py
- tests/test_document_type_aware_dashboard.py

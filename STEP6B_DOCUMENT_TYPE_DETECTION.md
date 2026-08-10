# LifeOS Document Brain — Step 6B

Step 6B adds the lightweight backend document-type detector.

Flow implemented in this step:

PDF text
-> representative sample (max 12,000 characters)
-> provider classification request
-> strict validation against Step 6A profiles
-> ownership-aware workflow result

The detector does NOT run the full document analysis.
The result is NOT saved as a completed analysis.
Step 6C will expose it in the UI so the user can confirm or change the type.

New files:
- services/document_type_detection_service.py
- services/document_type_detection_workflow_service.py
- tests/test_document_type_detection_service.py
- tests/test_document_type_detection_workflow_service.py

Updated:
- services/document_type_profile_service.py
- tests/test_document_type_profile_service.py

No database migration is required.

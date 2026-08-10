# LifeOS Document Brain — Step 6A

This patch adds the central document-type profile registry.

Step 6A deliberately does NOT call Gemini and does NOT change the UI yet.
It creates the single source of truth that Step 6B–6E will use for:

- automatic type detection
- confirmation dropdown options
- type-specific analysis prompts
- type-specific dashboard sections
- validation
- tests

Supported types:
1. Requirements Document
2. Research Paper
3. Meeting Notes
4. Project Plan
5. Technical Documentation
6. Lecture Material
7. Policy
8. Contract
9. General Reference

Policy and Contract are now separate profiles.

Run:
python -m py_compile services\document_type_profile_service.py services\document_analysis_service.py
python -m pytest tests\test_document_type_profile_service.py -v

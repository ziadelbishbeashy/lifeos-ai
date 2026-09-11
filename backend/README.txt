LifeOS Phase 1 Step 2 — Source-ID Answerability Verifier Fix

Root cause
----------
The verifier asked Gemini to copy an exact evidence quotation. Gemini often
returned a correct source number but slightly paraphrased the quotation. The
backend then rejected the result because the generated sentence was not an
exact substring of the retrieved source. Retrying the same instruction did not
solve the architectural mismatch.

Fix
---
1. Gemini now returns only answerable, confidence, reason, and source_ids.
2. LifeOS validates that every source ID exists in the supplied retrieval set.
3. LifeOS builds evidence previews directly from the trusted source text.
4. Model-generated evidence text is never trusted or substring-matched.
5. Legacy supports responses remain temporarily accepted, but only their
   source_id values are used; their evidence strings are ignored.
6. The question workflow version is v7 so old completed v6 answers are not
   reused.

Replace
-------
services/document_answerability_service.py
services/document_question_workflow_service.py
tests/test_document_answerability_service.py

No database migration is required.

Commands
--------
python -m py_compile services\document_answerability_service.py
python -m py_compile services\document_question_workflow_service.py
python -m pytest tests\test_document_answerability_service.py -v
python -m pytest tests\test_document_question_workflow_service.py -v
python -m pytest

Real check
----------
Restart Flask, then rerun the direct verifier script. A positive result should
return valid source IDs without raising an evidence-substring validation error.

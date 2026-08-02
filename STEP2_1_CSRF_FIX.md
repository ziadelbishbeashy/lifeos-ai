# LifeOS Architecture Step 2.1 — Form Protection Fix

This patch adds an explicit CSRF hidden input to every POST form while keeping
JavaScript-based protection as a fallback for dynamically inserted forms.

It fixes state-changing actions such as logout and project creation failing
after Step 2.

No database or model changes are included.

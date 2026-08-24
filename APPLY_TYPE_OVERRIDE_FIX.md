# LifeOS full-separation type override regression fix

This patch fixes the remaining regression:

`test_user_override_message_is_rendered`

The saved analysis metadata already contains both the detected and confirmed document type. The presentation model now preserves both values when a user overrides the detected type.

Native React shows a compact status such as:

`Type adjusted · Technical Documentation → Research Paper`

The dormant Jinja compatibility view renders the same metadata so the historical backend regression suite remains green until those legacy UI tests are intentionally retired.

## Apply
Copy the `backend` and `frontend` folders over the project root, preserving paths.

Then from the project root run:

```powershell
.\scripts\check-react-parity.ps1
```

Expected backend regression result: all tests pass (the SQLAlchemy Query.get warnings may remain and are non-blocking).

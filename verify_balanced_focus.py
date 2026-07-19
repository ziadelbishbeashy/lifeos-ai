from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHECKS = {
    "balanced focus template": (ROOT / "templates" / "focus_mode.html", "focus-studio-setup"),
    "calm active session": (ROOT / "templates" / "focus_mode.html", "focus-calm-session"),
    "session tools": (ROOT / "templates" / "focus_mode.html", "Session tools"),
    "break overlay": (ROOT / "templates" / "focus_mode.html", "focusBreakOverlay"),
    "distraction conversion route": (ROOT / "routes" / "focus_routes.py", "convert_distraction_to_task"),
    "focus page body class": (ROOT / "templates" / "base.html", "focus-page-shell"),
    "balanced focus styles": (ROOT / "static" / "css" / "style.css", "BALANCED FOCUS STUDIO"),
    "balanced focus logic": (ROOT / "static" / "js" / "focus.js", "lifeos-focus-pending-settings"),
}

failed = False
for name, (path, expected) in CHECKS.items():
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    ok = expected in content
    print(f"{'PASS' if ok else 'FAIL'} — {name}")
    failed = failed or not ok

raise SystemExit(1 if failed else 0)

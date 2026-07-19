from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
checks = {
    "minimal focus template": (ROOT / "templates" / "focus_mode.html", "minimal-focus-prepare"),
    "immersive focus template": (ROOT / "templates" / "focus_mode.html", "minimal-focus-active"),
    "insights template": (ROOT / "templates" / "focus_insights.html", "focus-insights-page"),
    "focus route passes active session": (ROOT / "routes" / "focus_routes.py", "active_session=session"),
    "parked thought route": (ROOT / "routes" / "focus_routes.py", "def add_distraction"),
    "insights route": (ROOT / "routes" / "focus_routes.py", "def insights"),
    "immersive body class": (ROOT / "templates" / "base.html", "focus-immersive-active"),
    "minimal focus JavaScript": (ROOT / "static" / "js" / "focus.js", "parkThoughtForm"),
    "minimal focus CSS": (ROOT / "static" / "css" / "style.css", "PHASE 5.5 — MINIMAL FOCUS MODE"),
    "SQL migration": (ROOT / "sql" / "phase5_5_minimal_focus_mode.sql", "focus_distractions"),
}

failed = False
for label, (path, marker) in checks.items():
    ok = path.exists() and marker in path.read_text(encoding="utf-8")
    print(f"{'PASS' if ok else 'FAIL'}  {label}")
    failed = failed or not ok

if failed:
    sys.exit(1)
print("\nMinimal Focus Mode files are synchronized.")

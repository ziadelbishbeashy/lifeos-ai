"""Verify that all synchronized Focus Studio v2.2.1 files are in the active project."""
from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent

checks: list[tuple[str, bool, str]] = []

def add(name: str, ok: bool, detail: str) -> None:
    checks.append((name, ok, detail))

route_path = ROOT / "routes" / "focus_routes.py"
model_path = ROOT / "models.py"
template_path = ROOT / "templates" / "focus_mode.html"
base_path = ROOT / "templates" / "base.html"
css_path = ROOT / "static" / "css" / "focus.css"
js_path = ROOT / "static" / "js" / "focus.js"

for path in [route_path, model_path, template_path, base_path, css_path, js_path]:
    add(f"File exists: {path.relative_to(ROOT)}", path.exists(), str(path))

if route_path.exists():
    route_source = route_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(route_source)
        functions = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        required = {
            "focus_mode", "save_preferences", "start_focus", "pause_focus",
            "resume_focus", "extend_focus", "advance_phase", "add_distraction",
            "convert_distraction", "finish_focus", "cancel_focus",
        }
        missing = sorted(required - functions)
        add("All Focus routes exist", not missing, f"Missing: {missing}" if missing else "All required functions found")
    except SyntaxError as exc:
        add("focus_routes.py syntax", False, str(exc))

    add("Route sync marker", 'FOCUS_STUDIO_SYNC_VERSION = "2.2.1-final"' in route_source, "Expected v2.2.1-final")
    for argument in ["preferences=preferences", "analytics=analytics", "achievements=achievements", "coach=task_coach_recommendation(tasks)"]:
        add(f"Template context: {argument}", argument in route_source, argument)

if model_path.exists():
    model_source = model_path.read_text(encoding="utf-8")
    for model in ["class FocusSession", "class FocusPreference", "class FocusDistraction"]:
        add(f"Model exists: {model.removeprefix('class ')}", model in model_source, model)

if template_path.exists():
    template_source = template_path.read_text(encoding="utf-8")
    add("Template fallback for preferences", "focus_preferences = preferences if preferences is defined" in template_source, "Safe Jinja fallback")
    add("Template fallback for analytics", "focus_analytics = analytics if analytics is defined" in template_source, "Safe Jinja fallback")
    add("Preferences form path", 'action="/focus/preferences"' in template_source, "/focus/preferences")
    add("Template sync marker", "data-focus-version=" in template_source, "Expected data-focus-version")

if base_path.exists():
    base_source = base_path.read_text(encoding="utf-8")
    add("Base template loads page CSS", "{% block head_extra %}{% endblock %}" in base_source, "head_extra block")

failed = False
print("\nLifeOS Focus Studio verification\n" + "=" * 40)
for name, ok, detail in checks:
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"      {detail}")
        failed = True

if failed:
    print("\nVerification failed. The files were not extracted into the active LifeOS project root.")
    sys.exit(1)

print("\nAll synchronized Focus Studio v2.2.1 files are installed correctly.")

"""UI contract tests for the complete Step 9 approval workflow."""

from pathlib import Path

from jinja2 import Environment


ROOT = Path(__file__).resolve().parents[1]


def test_document_suggestion_component_has_locked_user_actions():
    template = (
        ROOT
        / "templates"
        / "_document_task_suggestions.html"
    ).read_text(encoding="utf-8")

    assert "Create selected" in template
    assert "Edit first" in template
    assert "View existing" in template
    assert "Create anyway" in template
    assert "Ignore" in template
    assert "Possible existing task" in template


def test_edit_first_template_contains_all_approved_editable_fields():
    template = (
        ROOT
        / "templates"
        / "document_suggestion_edit.html"
    ).read_text(encoding="utf-8")

    for field in (
        'name="title"',
        'name="description"',
        'name="priority"',
        'name="deadline"',
        'name="tags"',
        'name="status"',
        'name="project_id"',
    ):
        assert field in template

    assert "Trusted source" in template

    # Ignore harmless HTML/Jinja source formatting and line wrapping.
    normalised_template = " ".join(
        template.split()
    )
    assert "not editable" in normalised_template


def test_document_and_project_templates_both_surface_suggestions():
    document_template = (
        ROOT / "templates" / "document_details.html"
    ).read_text(encoding="utf-8")
    project_template = (
        ROOT / "templates" / "project_details.html"
    ).read_text(encoding="utf-8")

    assert "render_document_task_suggestions" in document_template
    assert "bulk_create_suggestions_route" in document_template
    assert "render_document_task_suggestions" in project_template
    assert "bulk_create_document_suggestions_route" in project_template


def test_step9_templates_parse():
    environment = Environment()

    for name in (
        "_document_task_suggestions.html",
        "document_suggestion_edit.html",
        "document_details.html",
        "project_details.html",
        "tasks.html",
        "edit_task.html",
    ):
        environment.parse(
            (ROOT / "templates" / name).read_text(encoding="utf-8")
        )

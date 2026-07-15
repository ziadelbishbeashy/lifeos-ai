from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import db
from models import Project


project_bp = Blueprint("project_bp", __name__)


def _parse_date(value):
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()
    return None


def _project_fields_from_form(form):
    no_deadline = form.get("no_deadline") == "on"

    progress = form.get("progress")
    progress = int(progress) if progress else 0

    return {
        "title": form.get("title"),
        "project_type": form.get("project_type"),
        "description": form.get("description"),
        "goal": form.get("goal"),
        "tech_stack": form.get("tech_stack"),
        "project_folder": form.get("project_folder"),
        "github_link": form.get("github_link"),
        "demo_link": form.get("demo_link"),
        "start_date": _parse_date(form.get("start_date")),
        "deadline": None if no_deadline else _parse_date(form.get("deadline")),
        "status": form.get("status"),
        "priority": form.get("priority"),
        "current_phase": form.get("current_phase"),
        "progress": progress,
    }


@project_bp.route("/projects", methods=["GET", "POST"])
def projects():
    if request.method == "POST":
        if not request.form.get("title"):
            flash("Project title is required.", "error")
            return redirect(url_for("project_bp.projects"))

        fields = _project_fields_from_form(request.form)
        new_project = Project(**fields)

        db.session.add(new_project)
        db.session.commit()

        flash(f'Project "{new_project.title}" created successfully.', "success")
        return redirect(url_for("project_bp.projects"))

    all_projects = Project.query.order_by(Project.created_at.desc()).all()

    return render_template("projects.html", projects=all_projects)


@project_bp.route("/projects/<int:project_id>")
def project_details(project_id):
    project = Project.query.get_or_404(project_id)

    return render_template("project_details.html", project=project)


@project_bp.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)

    if request.method == "POST":
        if not request.form.get("title"):
            flash("Project title is required.", "error")
            return redirect(url_for("project_bp.edit_project", project_id=project.id))

        fields = _project_fields_from_form(request.form)
        for key, value in fields.items():
            setattr(project, key, value)

        db.session.commit()

        flash(f'Project "{project.title}" updated successfully.', "success")
        return redirect(url_for("project_bp.project_details", project_id=project.id))

    return render_template("edit_project.html", project=project)


@project_bp.route("/projects/<int:project_id>/delete", methods=["POST"])
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    title = project.title

    db.session.delete(project)
    db.session.commit()

    flash(f'Project "{title}" deleted.', "success")
    return redirect(url_for("project_bp.projects"))

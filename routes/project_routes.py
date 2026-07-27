"""HTTP routes for the LifeOS Projects experience."""

from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from services.project_service import (
    ProjectNotFoundError,
    ProjectPersistenceError,
    ProjectValidationError,
    build_project_input,
    build_project_workspace,
    build_projects_overview,
    create_project,
    delete_project as delete_project_record,
    require_owned_project,
    update_project,
)


project_bp = Blueprint("project_bp", __name__)


def _owned_project_or_404(project_id: int):
    """Translate ownership-safe service lookup into a neutral HTTP 404."""

    try:
        return require_owned_project(project_id, current_user.id)
    except ProjectNotFoundError:
        abort(404)


@project_bp.route("/projects", methods=["GET", "POST"])
@login_required
def projects():
    if request.method == "POST":
        project_data = build_project_input(request.form)

        try:
            project = create_project(current_user.id, project_data)
            flash(
                f'Project "{project.title}" created successfully.',
                "success",
            )
        except ProjectValidationError as error:
            flash(str(error), "error")
        except ProjectPersistenceError:
            current_app.logger.exception("LifeOS could not create a project.")
            flash("The project could not be created.", "error")

        return redirect(url_for("project_bp.projects"))

    overview = build_projects_overview(current_user.id)
    return render_template("projects.html", **overview)


@project_bp.route("/projects/<int:project_id>")
@login_required
def project_details(project_id):
    try:
        workspace = build_project_workspace(project_id, current_user.id)
    except ProjectNotFoundError:
        abort(404)

    return render_template("project_details.html", **workspace)


@project_bp.route(
    "/projects/<int:project_id>/edit",
    methods=["GET", "POST"],
)
@login_required
def edit_project(project_id):
    project = _owned_project_or_404(project_id)

    if request.method == "POST":
        project_data = build_project_input(request.form)

        try:
            project = update_project(project, project_data)
            flash(
                f'Project "{project.title}" updated successfully.',
                "success",
            )
        except ProjectValidationError as error:
            flash(str(error), "error")
            return redirect(
                url_for("project_bp.edit_project", project_id=project.id)
            )
        except ProjectPersistenceError:
            current_app.logger.exception(
                "LifeOS could not update project %s.",
                project.id,
            )
            flash("The project could not be updated.", "error")
            return redirect(
                url_for("project_bp.edit_project", project_id=project.id)
            )

        return redirect(
            url_for("project_bp.project_details", project_id=project.id)
        )

    return render_template("edit_project.html", project=project)


@project_bp.route(
    "/projects/<int:project_id>/delete",
    methods=["POST"],
)
@login_required
def delete_project(project_id):
    project = _owned_project_or_404(project_id)

    try:
        project_title = delete_project_record(project)
        flash(f'Project "{project_title}" deleted.', "success")
    except ProjectPersistenceError:
        current_app.logger.exception(
            "LifeOS could not delete project %s.",
            project.id,
        )
        flash("The project could not be deleted.", "error")

    return redirect(url_for("project_bp.projects"))

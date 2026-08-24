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

from services.document_task_action_service import (
    DocumentSuggestionNotFoundError,
    DocumentSuggestionPersistenceError,
    DocumentSuggestionWorkflowError,
    bulk_create_document_suggestions,
)

from services.project_question_workflow_service import (
    ProjectQuestionNotFoundError,
    ProjectQuestionNotReadyError,
    ProjectQuestionWorkflowError,
    ask_owned_project_documents,
)

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


@project_bp.post("/projects/<int:project_id>/questions")
@login_required
def ask_project_documents_route(project_id):
    """Ask one grounded question across every readable PDF in the project."""

    _owned_project_or_404(project_id)

    question_text = request.form.get("question", "")
    force = request.form.get("force") == "1"

    try:
        result = ask_owned_project_documents(
            project_id=project_id,
            user_id=current_user.id,
            question_text=question_text,
            force=force,
        )

    except ProjectQuestionNotFoundError:
        abort(404)

    except ProjectQuestionNotReadyError as error:
        flash(str(error), "warning")

    except ProjectQuestionWorkflowError as error:
        current_app.logger.warning(
            "Project document question failed for project %s: %s",
            project_id,
            type(error).__name__,
        )
        flash(str(error), "error")

    else:
        if result.reused_existing:
            flash(
                "LifeOS found an existing answer for this unchanged project document set.",
                "info",
            )
        elif result.question.sources:
            flash(
                "Your project document question was answered with grounded sources.",
                "success",
            )
        else:
            flash(
                "LifeOS could not find enough evidence in the linked PDFs to answer that question.",
                "info",
            )

    return redirect(
        url_for(
            "project_bp.project_details",
            project_id=project_id,
        )
        + "#ask-project"
    )


@project_bp.post(
    "/projects/<int:project_id>/document-suggestions/bulk-create"
)
@login_required
def bulk_create_document_suggestions_route(project_id):
    """Create selected document-derived tasks from the Project Studio."""

    _owned_project_or_404(project_id)

    try:
        result = bulk_create_document_suggestions(
            suggestion_ids=request.form.getlist("suggestion_ids"),
            user_id=current_user.id,
            project_id=project_id,
        )

    except DocumentSuggestionNotFoundError:
        abort(404)

    except DocumentSuggestionWorkflowError as error:
        flash(str(error), "warning")

    except DocumentSuggestionPersistenceError as error:
        current_app.logger.exception(
            "Could not bulk-create project document suggestions for project %s.",
            project_id,
        )
        flash(str(error), "error")

    else:
        if result.created_count:
            flash(
                f"Created {result.created_count} task"
                f"{'s' if result.created_count != 1 else ''} from document suggestions.",
                "success",
            )

        if result.duplicate_count:
            flash(
                f"Skipped {result.duplicate_count} possible duplicate"
                f"{'s' if result.duplicate_count != 1 else ''}. Review them individually.",
                "warning",
            )

        if not result.created_count and not result.duplicate_count:
            flash(
                "The selected suggestions were already handled.",
                "info",
            )

    return redirect(
        url_for(
            "project_bp.project_details",
            project_id=project_id,
        )
    )


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

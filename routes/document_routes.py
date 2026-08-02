"""Document Brain web routes."""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
    abort,
)
from flask_login import current_user, login_required

from services.document_access_service import (
    DocumentPersistenceError,
    DocumentValidationError,
    list_owned_documents,
)
from services.document_service import (
    DocumentUploadError,
    create_project_pdf_document,
)
from services.pdf_service import PDFValidationError
from services.project_service import list_owned_projects
from storage.base import StorageError

from models import Document, DocumentAIAnalysis, Project , DocumentTaskSuggestion

from services.document_ai_workflow_service import (
    DocumentAnalysisWorkflowError,
    DocumentNotFoundError,
    DocumentNotReadyError,
    analyse_owned_document,
)
from services.document_task_action_service import (
    DocumentSuggestionNotFoundError,
    DocumentSuggestionPersistenceError,
    DocumentSuggestionWorkflowError,
    approve_document_suggestion,
    link_suggestion_to_existing_task,
    reject_document_suggestion,
    require_owned_document_suggestion,
)

from services.document_question_workflow_service import (
    DocumentQuestionNotFoundError,
    DocumentQuestionNotReadyError,
    DocumentQuestionWorkflowError,
    ask_owned_document,
    list_owned_document_questions,
)

document_bp = Blueprint(
    "document_bp",
    __name__,
    url_prefix="/documents",
)


@document_bp.route("/", methods=["GET", "POST"])
@login_required
def documents():
    """Display owned documents and process PDF uploads."""

    if request.method == "POST":
        raw_project_id = request.form.get(
            "project_id",
            "",
        ).strip()

        try:
            project_id = int(raw_project_id)

        except (TypeError, ValueError):
            flash(
                "Please select a valid project.",
                "error",
            )

            return redirect(
                url_for("document_bp.documents")
            )

        upload = request.files.get("document")

        configured_limit = current_app.config.get(
            "MAX_CONTENT_LENGTH"
        )

        max_bytes = int(
            configured_limit or 25 * 1024 * 1024
        )

        try:
            result = create_project_pdf_document(
                upload,
                owner_id=current_user.id,
                project_id=project_id,
                max_bytes=max_bytes,
            )

        except (
            PDFValidationError,
            DocumentValidationError,
        ) as error:
            flash(
                str(error),
                "error",
            )

        except (
            DocumentPersistenceError,
            DocumentUploadError,
            StorageError,
        ):
            current_app.logger.exception(
                "Document upload failed for user %s.",
                current_user.id,
            )

            flash(
                "LifeOS could not save the document. "
                "Please try again.",
                "error",
            )

        else:
            if not result.extraction_succeeded:
                flash(
                    f'"{result.original_name}" was uploaded safely, '
                    "but its text could not be extracted.",
                    "warning",
                )

            elif result.pages_with_text == 0:
                flash(
                    f'"{result.original_name}" was uploaded safely. '
                    "No readable text was found, so this PDF may "
                    "require OCR.",
                    "warning",
                )

            elif not result.indexing_succeeded:
                current_app.logger.warning(
                    "Document chunk indexing failed for document %s: %s",
                    result.document.id,
                    result.indexing_message,
                )

                flash(
                    f'"{result.original_name}" was uploaded and its '
                    "text was extracted, but the searchable document "
                    "index could not be created. It can be retried later.",
                    "warning",
                )

            else:
                chunk_word = (
                    "chunk"
                    if result.chunk_count == 1
                    else "chunks"
                )

                flash(
                    f'"{result.original_name}" was uploaded, text was '
                    f"extracted from {result.pages_with_text} page(s), "
                    f"and {result.chunk_count} searchable "
                    f"{chunk_word} were created.",
                    "success",
                )

        return redirect(
            url_for("document_bp.documents")
        )

    documents_list = list_owned_documents(
        current_user.id
    )

    projects = list_owned_projects(
        current_user.id
    )

    return render_template(
        "documents.html",
        documents=documents_list,
        projects=projects,
    )

@document_bp.get("/<int:document_id>")
@login_required
def document_details(document_id):
    """Display one document and its latest AI analysis."""

    document = (
        Document.query
        .join(
            Project,
            Document.project_id == Project.id,
        )
        .filter(
            Document.id == document_id,
            Project.user_id == current_user.id,
        )
        .first()
    )

    if document is None:
        abort(404)

    latest_analysis = (
        DocumentAIAnalysis.query
        .filter_by(
            document_id=document.id,
            user_id=current_user.id,
            status="Completed",
        )
        .order_by(
            DocumentAIAnalysis.created_at.desc(),
            DocumentAIAnalysis.id.desc(),
        )
        .first()
    )
    suggestions = []

    if latest_analysis is not None:
        suggestions = (
            DocumentTaskSuggestion.query
            .filter_by(
                analysis_id=latest_analysis.id,
                document_id=document.id,
                user_id=current_user.id,
            )
            .order_by(
                DocumentTaskSuggestion.created_at.asc(),
                DocumentTaskSuggestion.id.asc(),
            )
            .all()
        )
    question_history = list_owned_document_questions(
    document_id=document.id,
    user_id=current_user.id,
    limit=20,
    )

    latest_attempt = (
        DocumentAIAnalysis.query
        .filter_by(
            document_id=document.id,
            user_id=current_user.id,
        )
        .order_by(
            DocumentAIAnalysis.created_at.desc(),
            DocumentAIAnalysis.id.desc(),
        )
        .first()
    )

    return render_template(
        "document_details.html",
        document=document,
        analysis=latest_analysis,
        suggestions=suggestions,
        latest_attempt=latest_attempt,
        question_history=question_history,
    )


@document_bp.post("/<int:document_id>/analyse")
@login_required
def analyse_document_route(document_id):
    """Run AI analysis for an owned document."""

    force = request.form.get("force") == "1"

    try:
        result = analyse_owned_document(
            document_id=document_id,
            user_id=current_user.id,
            force=force,
        )

    except DocumentNotFoundError:
        abort(404)

    except DocumentNotReadyError as error:
        flash(
            str(error),
            "warning",
        )

    except DocumentAnalysisWorkflowError as error:
        current_app.logger.exception(
            "Document analysis failed for document %s.",
            document_id,
        )

        flash(
            str(error),
            "error",
        )

    else:
        if result.reused_existing:
            flash(
                "The current document analysis is already up to date.",
                "info",
            )
        else:
            flash(
                "Document analysis completed successfully.",
                "success",
            )

    return redirect(
        url_for(
            "document_bp.document_details",
            document_id=document_id,
        )
    )


@document_bp.post(
    "/<int:document_id>/suggestions/"
    "<int:suggestion_id>/approve"
)
@login_required
def approve_suggestion_route(
    document_id,
    suggestion_id,
):
    """Approve a suggestion and create a project task."""

    allow_duplicate = (
        request.form.get(
            "allow_possible_duplicate"
        )
        == "1"
    )

    try:
        suggestion = require_owned_document_suggestion(
            document_id=document_id,
            suggestion_id=suggestion_id,
            user_id=current_user.id,
        )

        task = approve_document_suggestion(
            suggestion=suggestion,
            user_id=current_user.id,
            allow_possible_duplicate=allow_duplicate,
        )

    except DocumentSuggestionNotFoundError:
        abort(404)

    except DocumentSuggestionWorkflowError as error:
        flash(
            str(error),
            "warning",
        )

    except DocumentSuggestionPersistenceError as error:
        current_app.logger.exception(
            "Could not approve document suggestion %s.",
            suggestion_id,
        )

        flash(
            str(error),
            "error",
        )

    else:
        flash(
            f'Task "{task.title}" was created successfully.',
            "success",
        )

    return redirect(
        url_for(
            "document_bp.document_details",
            document_id=document_id,
        )
    )


@document_bp.post(
    "/<int:document_id>/suggestions/"
    "<int:suggestion_id>/link"
)
@login_required
def link_suggestion_route(
    document_id,
    suggestion_id,
):
    """Link a suggestion to an existing project task."""

    try:
        suggestion = require_owned_document_suggestion(
            document_id=document_id,
            suggestion_id=suggestion_id,
            user_id=current_user.id,
        )

        task = link_suggestion_to_existing_task(
            suggestion=suggestion,
            user_id=current_user.id,
        )

    except DocumentSuggestionNotFoundError:
        abort(404)

    except DocumentSuggestionWorkflowError as error:
        flash(
            str(error),
            "warning",
        )

    except DocumentSuggestionPersistenceError as error:
        current_app.logger.exception(
            "Could not link document suggestion %s.",
            suggestion_id,
        )

        flash(
            str(error),
            "error",
        )

    else:
        flash(
            f'Suggestion linked to existing task "{task.title}".',
            "success",
        )

    return redirect(
        url_for(
            "document_bp.document_details",
            document_id=document_id,
        )
    )


@document_bp.post(
    "/<int:document_id>/suggestions/"
    "<int:suggestion_id>/reject"
)
@login_required
def reject_suggestion_route(
    document_id,
    suggestion_id,
):
    """Reject a Document Brain suggestion."""

    try:
        suggestion = require_owned_document_suggestion(
            document_id=document_id,
            suggestion_id=suggestion_id,
            user_id=current_user.id,
        )

        result = reject_document_suggestion(
            suggestion
        )

    except DocumentSuggestionNotFoundError:
        abort(404)

    except DocumentSuggestionWorkflowError as error:
        flash(
            str(error),
            "warning",
        )

    except DocumentSuggestionPersistenceError as error:
        current_app.logger.exception(
            "Could not reject document suggestion %s.",
            suggestion_id,
        )

        flash(
            str(error),
            "error",
        )

    else:
        if result == "already_rejected":
            flash(
                "This suggestion was already rejected.",
                "info",
            )
        else:
            flash(
                "Document suggestion rejected.",
                "success",
            )

    return redirect(
        url_for(
            "document_bp.document_details",
            document_id=document_id,
        )
    )


@document_bp.post("/<int:document_id>/questions")
@login_required
def ask_document_question_route(document_id):
    """Ask and save a grounded question about one document."""

    question_text = request.form.get(
        "question",
        "",
    )

    force = request.form.get("force") == "1"

    try:
        result = ask_owned_document(
            document_id=document_id,
            user_id=current_user.id,
            question_text=question_text,
            force=force,
        )

    except DocumentQuestionNotFoundError:
        abort(404)

    except DocumentQuestionNotReadyError as error:
        flash(
            str(error),
            "warning",
        )

    except DocumentQuestionWorkflowError as error:
        current_app.logger.exception(
            "Document question failed for document %s.",
            document_id,
        )

        flash(
            str(error),
            "error",
        )

    else:
        if result.reused_existing:
            flash(
                "LifeOS found an existing answer for this question.",
                "info",
            )
        else:
            flash(
                "Your document question was answered successfully.",
                "success",
            )

    return redirect(
        url_for(
            "document_bp.document_details",
            document_id=document_id,
        )
        + "#ask-document"
    )
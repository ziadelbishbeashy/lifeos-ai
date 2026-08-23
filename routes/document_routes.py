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
    jsonify,
    send_file,
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
from storage.service import get_storage

from models import Document, DocumentAIAnalysis, Project , DocumentTaskSuggestion

from services.document_ai_workflow_service import (
    DocumentAnalysisWorkflowError,
    DocumentNotFoundError,
    DocumentNotReadyError,
    analyse_owned_document,
)
from services.document_task_action_service import (
    DocumentSuggestionDuplicateError,
    DocumentSuggestionNotFoundError,
    DocumentSuggestionPersistenceError,
    DocumentSuggestionWorkflowError,
    approve_document_suggestion,
    build_suggestion_task_input,
    bulk_create_document_suggestions,
    default_suggestion_task_input,
    link_suggestion_to_existing_task,
    list_document_suggestions,
    preview_possible_duplicate,
    reject_document_suggestion,
    require_owned_document_suggestion,
)

from services.document_overview_service import (
    build_structured_document_overview,
)
from services.document_type_detection_service import (
    ALLOWED_DETECTION_CONFIDENCE,
)
from services.document_type_detection_workflow_service import (
    DocumentTypeDetectionNotFoundError,
    DocumentTypeDetectionNotReadyError,
    DocumentTypeDetectionWorkflowError,
    detect_owned_document_type,
)
from services.document_type_profile_service import (
    document_type_choices,
    resolve_document_type_key,
)
from services.document_type_workspace_service import (
    build_document_type_workspace,
)
from services.document_question_workflow_service import (
    NO_MATCH_ANSWER,
    DocumentQuestionNotFoundError,
    DocumentQuestionNotReadyError,
    DocumentQuestionWorkflowError,
    ask_owned_document,
    list_owned_document_questions,
)
from services.document_search_service import (
    DocumentSearchError,
    DocumentSearchNotFoundError,
    DocumentSearchNotReadyError,
    DocumentSearchValidationError,
    search_owned_document,
)
from services.document_navigation_service import (
    DocumentNavigationError,
    DocumentNavigationNotFoundError,
    DocumentNavigationNotReadyError,
    DocumentNavigationValidationError,
    get_owned_document_context,
    prepare_owned_document_file,
)
from services.document_pdf_search_service import (
    DocumentPDFSearchError,
    DocumentPDFSearchNotFoundError,
    DocumentPDFSearchNotReadyError,
    DocumentPDFSearchValidationError,
    search_owned_document_for_pdf,
)
from services.document_comparison_service import (
    DocumentComparisonNotFoundError,
    DocumentComparisonValidationError,
    list_owned_comparisons,
    require_owned_comparison,
)
from services.document_comparison_workflow_service import (
    DocumentComparisonPersistenceError,
    DocumentComparisonWorkflowError,
    compare_owned_documents,
)
from services.document_version_service import (
    DocumentVersionNotFoundError,
    DocumentVersionPersistenceError,
    DocumentVersionValidationError,
    create_new_document_version,
    get_owned_document_version_history,
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

    configured_limit = current_app.config.get(
        "MAX_CONTENT_LENGTH"
    )

    max_upload_bytes = int(
        configured_limit or 25 * 1024 * 1024
    )

    max_upload_mb = max(
        1,
        round(
            max_upload_bytes
            / (1024 * 1024)
        ),
    )

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

        try:
            result = create_project_pdf_document(
                upload,
                owner_id=current_user.id,
                project_id=project_id,
                max_bytes=max_upload_bytes,
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
        max_upload_bytes=max_upload_bytes,
        max_upload_mb=max_upload_mb,
    )


@document_bp.route(
    "/compare",
    methods=["GET", "POST"],
)
@login_required
def compare_documents():
    """Select two owned PDFs and run an ordered semantic comparison."""

    owned_documents = list_owned_documents(
        current_user.id
    )

    if request.method == "POST":
        document_a_id = request.form.get(
            "document_a_id",
            "",
        )

        document_b_id = request.form.get(
            "document_b_id",
            "",
        )

        force = (
            request.form.get(
                "force"
            )
            == "1"
        )

        try:
            result = compare_owned_documents(
                owner_id=current_user.id,
                document_a_id=document_a_id,
                document_b_id=document_b_id,
                force=force,
            )

        except DocumentComparisonValidationError as error:
            flash(
                str(error),
                "warning",
            )

            return redirect(
                url_for(
                    "document_bp.compare_documents",
                    document_a_id=document_a_id,
                    document_b_id=document_b_id,
                )
            )

        except DocumentComparisonNotFoundError:
            abort(404)

        except DocumentComparisonPersistenceError as error:
            current_app.logger.exception(
                "Document comparison persistence failed for user %s.",
                current_user.id,
            )

            flash(
                str(error),
                "error",
            )

            return redirect(
                url_for(
                    "document_bp.compare_documents",
                    document_a_id=document_a_id,
                    document_b_id=document_b_id,
                )
            )

        except DocumentComparisonWorkflowError as error:
            current_app.logger.exception(
                "Document comparison failed for user %s.",
                current_user.id,
            )

            flash(
                str(error),
                "error",
            )

            return redirect(
                url_for(
                    "document_bp.compare_documents",
                    document_a_id=document_a_id,
                    document_b_id=document_b_id,
                )
            )

        else:
            if result.reused_existing:
                flash(
                    "LifeOS found an up-to-date comparison for these documents.",
                    "info",
                )

            elif result.rejected_findings:
                flash(
                    "Comparison completed. LifeOS kept only the differences "
                    "that passed evidence verification.",
                    "success",
                )

            else:
                flash(
                    "Document comparison completed and verified.",
                    "success",
                )

            return redirect(
                url_for(
                    "document_bp.document_comparison_details",
                    comparison_id=result.comparison.id,
                )
            )

    selected_a_id = _optional_owned_document_selection(
        request.args.get(
            "document_a_id"
        ),
        owned_documents=owned_documents,
    )

    selected_b_id = _optional_owned_document_selection(
        request.args.get(
            "document_b_id"
        ),
        owned_documents=owned_documents,
    )

    comparisons = list_owned_comparisons(
        owner_id=current_user.id,
        limit=20,
    )

    return render_template(
        "document_compare.html",
        documents=owned_documents,
        comparisons=comparisons,
        selected_a_id=selected_a_id,
        selected_b_id=selected_b_id,
    )


@document_bp.get(
    "/comparisons/<int:comparison_id>"
)
@login_required
def document_comparison_details(
    comparison_id,
):
    """Display one owned, saved document comparison."""

    try:
        comparison = require_owned_comparison(
            comparison_id=comparison_id,
            owner_id=current_user.id,
        )

    except DocumentComparisonNotFoundError:
        abort(404)

    category_counts = _comparison_category_counts(
        comparison.findings
    )

    return render_template(
        "document_comparison_details.html",
        comparison=comparison,
        category_counts=category_counts,
    )


@document_bp.post(
    "/comparisons/<int:comparison_id>/rerun"
)
@login_required
def rerun_document_comparison(
    comparison_id,
):
    """Force a fresh comparison for the same owned ordered document pair."""

    try:
        comparison = require_owned_comparison(
            comparison_id=comparison_id,
            owner_id=current_user.id,
        )

        result = compare_owned_documents(
            owner_id=current_user.id,
            document_a_id=comparison.document_a_id,
            document_b_id=comparison.document_b_id,
            force=True,
        )

    except DocumentComparisonNotFoundError:
        abort(404)

    except DocumentComparisonValidationError as error:
        flash(
            str(error),
            "warning",
        )

        return redirect(
            url_for(
                "document_bp.document_comparison_details",
                comparison_id=comparison_id,
            )
        )

    except (
        DocumentComparisonWorkflowError,
        DocumentComparisonPersistenceError,
    ) as error:
        current_app.logger.exception(
            "Document comparison rerun failed for comparison %s.",
            comparison_id,
        )

        flash(
            str(error),
            "error",
        )

        return redirect(
            url_for(
                "document_bp.document_comparison_details",
                comparison_id=comparison_id,
            )
        )

    flash(
        "LifeOS generated a fresh verified comparison.",
        "success",
    )

    return redirect(
        url_for(
            "document_bp.document_comparison_details",
            comparison_id=result.comparison.id,
        )
    )


@document_bp.get("/<int:document_id>")
@login_required
def document_details(document_id):
    """Display one document and its latest AI analysis."""

    document = _find_owned_document_for_details(
        document_id
    )

    if document is None:
        abort(404)

    return _render_document_details(
        document=document,
    )


@document_bp.post("/<int:document_id>/versions")
@login_required
def upload_new_document_version_route(document_id):
    """Upload and activate an explicit new version of an owned project PDF."""

    configured_limit = current_app.config.get(
        "MAX_CONTENT_LENGTH"
    )

    max_upload_bytes = int(
        configured_limit or 25 * 1024 * 1024
    )

    upload = request.files.get(
        "document"
    )

    try:
        result = create_new_document_version(
            upload,
            source_document_id=document_id,
            owner_id=current_user.id,
            max_bytes=max_upload_bytes,
        )

    except DocumentVersionNotFoundError:
        abort(404)

    except (
        PDFValidationError,
        DocumentValidationError,
        DocumentVersionValidationError,
    ) as error:
        flash(
            str(error),
            "warning",
        )

        return redirect(
            url_for(
                "document_bp.document_details",
                document_id=document_id,
            )
        )

    except (
        DocumentPersistenceError,
        DocumentUploadError,
        DocumentVersionPersistenceError,
        StorageError,
    ) as error:
        current_app.logger.exception(
            "Document version upload failed for document %s.",
            document_id,
        )

        flash(
            str(error)
            or "LifeOS could not save the new document version.",
            "error",
        )

        return redirect(
            url_for(
                "document_bp.document_details",
                document_id=document_id,
            )
        )

    change = result.change_summary

    changed_count = (
        int(change.get("changed_page_count") or 0)
        + int(change.get("added_page_count") or 0)
        + int(change.get("removed_page_count") or 0)
    )

    if changed_count:
        change_message = (
            f"LifeOS detected page-level changes on {changed_count} page"
            f"{'s' if changed_count != 1 else ''}."
        )
    elif result.change_summary.get("content_changed"):
        change_message = (
            "LifeOS detected a file/content fingerprint change even though "
            "no page-level text difference was available."
        )
    else:
        change_message = (
            "LifeOS did not detect a material text or file fingerprint change."
        )

    flash(
        (
            f'"{result.current_document.filename}" is now '
            f'{result.current_document.version_label}. '
            f"{change_message} Superseded answers and analyses were marked "
            "outdated."
        ),
        "success",
    )

    if not result.upload_result.extraction_succeeded:
        flash(
            "The new version is current, but its text could not be extracted. "
            "It may require OCR before current project Q&A can use it.",
            "warning",
        )
    elif result.upload_result.pages_with_text == 0:
        flash(
            "The new version is current, but no readable text was found. "
            "It may require OCR before current project Q&A can use it.",
            "warning",
        )

    if (
        result.embedding_message
        and not result.embeddings_succeeded
    ):
        current_app.logger.warning(
            "Version %s semantic embedding preparation was deferred: %s",
            result.current_document.id,
            result.embedding_message,
        )

    return redirect(
        url_for(
            "document_bp.document_details",
            document_id=result.current_document.id,
        )
    )


@document_bp.post("/<int:document_id>/detect-type")
@login_required
def detect_document_type_route(document_id):
    """
    Detect a document type and show it for user confirmation.

    The detector does not run the full analysis. The returned page lets
    the user confirm LifeOS's suggestion or select a different type.
    """

    document = _find_owned_document_for_details(
        document_id
    )

    if document is None:
        abort(404)

    if document.is_historical_version:
        history = get_owned_document_version_history(
            document_id=document.id,
            owner_id=current_user.id,
        )

        flash(
            "This is a previous document version. Open the current version "
            "to detect its type or run a new analysis.",
            "warning",
        )

        return redirect(
            url_for(
                "document_bp.document_details",
                document_id=history.current_document.id,
            )
        )

    try:
        result = detect_owned_document_type(
            document_id=document_id,
            user_id=current_user.id,
        )

    except DocumentTypeDetectionNotFoundError:
        abort(404)

    except DocumentTypeDetectionNotReadyError as error:
        flash(
            str(error),
            "warning",
        )

        return redirect(
            url_for(
                "document_bp.document_details",
                document_id=document_id,
            )
        )

    except DocumentTypeDetectionWorkflowError as error:
        current_app.logger.exception(
            "Document type detection failed for document %s.",
            document_id,
        )

        flash(
            str(error),
            "error",
        )

        return redirect(
            url_for(
                "document_bp.document_details",
                document_id=document_id,
            )
        )

    return _render_document_details(
        document=result.document,
        type_detection=result.detection,
    )


def _optional_owned_document_selection(
    raw_document_id,
    *,
    owned_documents,
):
    """Return a selected ID only when it exists in the current owned list."""

    try:
        document_id = int(
            raw_document_id
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    owned_ids = {
        document.id
        for document in owned_documents
    }

    return (
        document_id
        if document_id in owned_ids
        else None
    )


def _comparison_category_counts(
    findings,
):
    counts = {
        "changed": 0,
        "added": 0,
        "removed": 0,
        "potential_conflict": 0,
    }

    for finding in findings:
        if not isinstance(
            finding,
            dict,
        ):
            continue

        category = finding.get(
            "category"
        )

        if category in counts:
            counts[
                category
            ] += 1

    return counts


def _find_owned_document_for_details(
    document_id: int,
) -> Document | None:
    """Return the document only when the current user owns its project."""

    return (
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


def _render_document_details(
    *,
    document: Document,
    type_detection=None,
    document_search=None,
):
    """Build all data required by the Document Brain details page."""

    analysis_query = (
        DocumentAIAnalysis.query
        .filter_by(
            document_id=document.id,
            user_id=current_user.id,
        )
    )

    if document.is_historical_version:
        analysis_query = analysis_query.filter(
            DocumentAIAnalysis.status.in_(
                [
                    "Outdated",
                    "Historical",
                    "Completed",
                ]
            )
        )
    else:
        analysis_query = analysis_query.filter_by(
            status="Completed"
        )

    latest_analysis = (
        analysis_query
        .order_by(
            DocumentAIAnalysis.created_at.desc(),
            DocumentAIAnalysis.id.desc(),
        )
        .first()
    )

    try:
        version_history = get_owned_document_version_history(
            document_id=document.id,
            owner_id=current_user.id,
        )
    except DocumentVersionNotFoundError:
        version_history = None

    try:
        suggestions = list_document_suggestions(
            document_id=document.id,
            user_id=current_user.id,
        )
    except DocumentSuggestionNotFoundError:
        suggestions = []

    overview = build_structured_document_overview(
        latest_analysis
    )

    type_workspace = build_document_type_workspace(
        latest_analysis
    )

    question_history = list_owned_document_questions(
        document_id=document.id,
        user_id=current_user.id,
        limit=50,
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
        overview=overview,
        suggestions=suggestions,
        latest_attempt=latest_attempt,
        question_history=question_history,
        type_detection=type_detection,
        document_type_choices=document_type_choices(),
        type_workspace=type_workspace,
        document_search=document_search,
        version_history=version_history,
    )


@document_bp.get("/<int:document_id>/search")
@login_required
def search_document_route(document_id):
    """Search real passages inside one owned document."""

    query = request.args.get(
        "q",
        "",
    )

    try:
        result = search_owned_document(
            document_id=document_id,
            user_id=current_user.id,
            query=query,
        )

    except DocumentSearchNotFoundError:
        abort(404)

    except (
        DocumentSearchNotReadyError,
        DocumentSearchValidationError,
    ) as error:
        flash(
            str(error),
            "warning",
        )

        return redirect(
            url_for(
                "document_bp.document_details",
                document_id=document_id,
            )
            + "#search-document"
        )

    except DocumentSearchError as error:
        current_app.logger.exception(
            "Document search failed for document %s.",
            document_id,
        )

        flash(
            str(error),
            "error",
        )

        return redirect(
            url_for(
                "document_bp.document_details",
                document_id=document_id,
            )
            + "#search-document"
        )

    return _render_document_details(
        document=result.document,
        document_search=result,
    )


@document_bp.get("/<int:document_id>/semantic-search")
@login_required
def semantic_search_document_route(document_id):
    """Return reader-friendly semantic matches for the embedded PDF."""

    query = request.args.get(
        "q",
        "",
    )

    try:
        result = search_owned_document_for_pdf(
            document_id=document_id,
            user_id=current_user.id,
            query=query,
        )

    except DocumentPDFSearchNotFoundError:
        abort(404)

    except DocumentPDFSearchValidationError as error:
        return jsonify(
            {
                "ok": False,
                "message": str(error),
            }
        ), 400

    except DocumentPDFSearchNotReadyError as error:
        return jsonify(
            {
                "ok": False,
                "message": str(error),
            }
        ), 409

    except DocumentPDFSearchError:
        current_app.logger.exception(
            "Semantic PDF search failed for document %s.",
            document_id,
        )

        return jsonify(
            {
                "ok": False,
                "message": (
                    "LifeOS could not search this PDF right now."
                ),
            }
        ), 500

    return jsonify(
        {
            "ok": True,
            **result.as_dict(),
        }
    )


@document_bp.get("/<int:document_id>/file")
@login_required
def document_file_route(document_id):
    """Serve one owned original PDF for the Step 8 viewer."""

    try:
        file_info = prepare_owned_document_file(
            document_id=document_id,
            user_id=current_user.id,
        )

    except DocumentNavigationNotFoundError:
        abort(404)

    except DocumentNavigationValidationError:
        abort(404)

    except DocumentNavigationNotReadyError:
        abort(404)

    except DocumentNavigationError:
        current_app.logger.exception(
            "Could not prepare PDF navigation for document %s.",
            document_id,
        )
        abort(500)

    download_requested = request.args.get(
        "download"
    ) == "1"

    try:
        if file_info.local_path is not None:
            response = send_file(
                file_info.local_path,
                mimetype="application/pdf",
                as_attachment=download_requested,
                download_name=file_info.filename,
                conditional=True,
            )

        else:
            storage = get_storage()
            stream = storage.open(
                file_info.storage_key,
                "rb",
            )

            response = send_file(
                stream,
                mimetype="application/pdf",
                as_attachment=download_requested,
                download_name=file_info.filename,
                conditional=False,
            )

    except StorageError:
        current_app.logger.exception(
            "Could not stream PDF for document %s.",
            document_id,
        )
        abort(500)

    # This route is private and will be used by the embedded PDF viewer.
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"

    return response


@document_bp.get(
    "/<int:document_id>/context/<int:chunk_id>"
)
@login_required
def document_context_route(
    document_id,
    chunk_id,
):
    """Return trusted previous/current/next context for one source."""

    try:
        context = get_owned_document_context(
            document_id=document_id,
            user_id=current_user.id,
            chunk_id=chunk_id,
        )

    except DocumentNavigationNotFoundError:
        abort(404)

    except DocumentNavigationValidationError as error:
        return jsonify(
            {
                "ok": False,
                "message": str(error),
            }
        ), 400

    except DocumentNavigationNotReadyError as error:
        return jsonify(
            {
                "ok": False,
                "message": str(error),
            }
        ), 409

    except DocumentNavigationError:
        current_app.logger.exception(
            "Could not load source context for document %s, chunk %s.",
            document_id,
            chunk_id,
        )

        return jsonify(
            {
                "ok": False,
                "message": (
                    "LifeOS could not load the surrounding document context."
                ),
            }
        ), 500

    return jsonify(
        {
            "ok": True,
            **context.as_dict(),
        }
    )


@document_bp.post("/<int:document_id>/analyse")
@login_required
def analyse_document_route(document_id):
    """Run full analysis only after document-type confirmation."""

    force = request.form.get(
        "force"
    ) == "1"

    confirmed_document_type = request.form.get(
        "confirmed_document_type",
        "",
    ).strip()

    detected_document_type = request.form.get(
        "detected_document_type",
        "",
    ).strip()

    detection_confidence = request.form.get(
        "detection_confidence",
        "",
    ).strip().casefold()

    if not (
        confirmed_document_type
        and detected_document_type
    ):
        flash(
            "Detect the document type and confirm it before analysis.",
            "warning",
        )

        return redirect(
            url_for(
                "document_bp.document_details",
                document_id=document_id,
            )
        )

    resolved_confirmed_type = resolve_document_type_key(
        confirmed_document_type
    )

    if resolved_confirmed_type is None:
        flash(
            "Please choose a supported document type.",
            "warning",
        )

        return redirect(
            url_for(
                "document_bp.document_details",
                document_id=document_id,
            )
        )

    resolved_detected_type = resolve_document_type_key(
        detected_document_type
    )

    if resolved_detected_type is None:
        flash(
            "The detected document type is no longer valid. "
            "Please detect the type again.",
            "warning",
        )

        return redirect(
            url_for(
                "document_bp.document_details",
                document_id=document_id,
            )
        )

    if (
        detection_confidence
        not in ALLOWED_DETECTION_CONFIDENCE
    ):
        flash(
            "The document-type detection result expired or is invalid. "
            "Please detect the type again.",
            "warning",
        )

        return redirect(
            url_for(
                "document_bp.document_details",
                document_id=document_id,
            )
        )

    try:
        result = analyse_owned_document(
            document_id=document_id,
            user_id=current_user.id,
            force=force,
            confirmed_document_type=(
                resolved_confirmed_type
            ),
            detected_document_type=(
                resolved_detected_type
            ),
            detection_confidence=(
                detection_confidence
            ),
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
                "The current analysis for this document type "
                "is already up to date.",
                "info",
            )
        else:
            flash(
                "Type-aware document analysis completed successfully.",
                "success",
            )

    return redirect(
        url_for(
            "document_bp.document_details",
            document_id=document_id,
        )
    )


@document_bp.route(
    "/<int:document_id>/suggestions/<int:suggestion_id>/edit-create",
    methods=["GET", "POST"],
)
@login_required
def edit_create_suggestion_route(
    document_id,
    suggestion_id,
):
    """Review editable task fields, then explicitly create the task."""

    try:
        suggestion = require_owned_document_suggestion(
            document_id=document_id,
            suggestion_id=suggestion_id,
            user_id=current_user.id,
        )

        if suggestion.status != "Pending":
            flash(
                "This suggestion has already been handled.",
                "info",
            )
            return redirect(
                url_for(
                    "document_bp.document_details",
                    document_id=document_id,
                )
            )

        if request.method == "POST":
            task_input = build_suggestion_task_input(
                form=request.form,
                suggestion=suggestion,
                user_id=current_user.id,
            )

            allow_duplicate = (
                request.form.get("allow_possible_duplicate") == "1"
            )

            task = approve_document_suggestion(
                suggestion=suggestion,
                user_id=current_user.id,
                allow_possible_duplicate=allow_duplicate,
                task_input=task_input,
            )

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

        task_input = default_suggestion_task_input(
            suggestion=suggestion
        )

        possible_duplicate = preview_possible_duplicate(
            suggestion=suggestion,
            user_id=current_user.id,
            task_input=task_input,
        )

    except DocumentSuggestionNotFoundError:
        abort(404)

    except DocumentSuggestionDuplicateError as error:
        flash(str(error), "warning")
        task_input = build_suggestion_task_input(
            form=request.form,
            suggestion=suggestion,
            user_id=current_user.id,
        )
        possible_duplicate = error.task

    except DocumentSuggestionWorkflowError as error:
        flash(str(error), "warning")
        task_input = default_suggestion_task_input(
            suggestion=suggestion
        )
        possible_duplicate = preview_possible_duplicate(
            suggestion=suggestion,
            user_id=current_user.id,
            task_input=task_input,
        )

    except DocumentSuggestionPersistenceError as error:
        current_app.logger.exception(
            "Could not create edited document suggestion %s.",
            suggestion_id,
        )
        flash(str(error), "error")
        task_input = default_suggestion_task_input(
            suggestion=suggestion
        )
        possible_duplicate = None

    return render_template(
        "document_suggestion_edit.html",
        document=suggestion.document,
        suggestion=suggestion,
        task_input=task_input,
        projects=list_owned_projects(current_user.id),
        possible_duplicate=possible_duplicate,
    )


@document_bp.post(
    "/<int:document_id>/suggestions/bulk-create"
)
@login_required
def bulk_create_suggestions_route(document_id):
    """Create several explicitly selected non-duplicate suggestions."""

    try:
        result = bulk_create_document_suggestions(
            suggestion_ids=request.form.getlist("suggestion_ids"),
            user_id=current_user.id,
            document_id=document_id,
        )

    except DocumentSuggestionNotFoundError:
        abort(404)

    except DocumentSuggestionWorkflowError as error:
        flash(str(error), "warning")

    except DocumentSuggestionPersistenceError as error:
        current_app.logger.exception(
            "Could not bulk-create document suggestions for document %s.",
            document_id,
        )
        flash(str(error), "error")

    else:
        if result.created_count:
            flash(
                f"Created {result.created_count} task"
                f"{'s' if result.created_count != 1 else ''} from the selected suggestions.",
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

    except DocumentSuggestionDuplicateError as error:
        flash(
            str(error),
            "warning",
        )

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
                "This suggestion was already ignored.",
                "info",
            )
        else:
            flash(
                "Document suggestion ignored.",
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

    selected_context_text = request.form.get(
        "selected_context_text",
        "",
    )

    selected_context_page = request.form.get(
        "selected_context_page",
        "",
    )

    selected_context_section = request.form.get(
        "selected_context_section",
        "",
    )

    try:
        result = ask_owned_document(
            document_id=document_id,
            user_id=current_user.id,
            question_text=question_text,
            force=force,
            selected_context_text=selected_context_text,
            selected_context_page=selected_context_page,
            selected_context_section=selected_context_section,
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
            saved_question = getattr(
                result,
                "question",
                None,
            )

            saved_answer = str(
                getattr(
                    saved_question,
                    "answer",
                    "",
                )
                or ""
            ).strip()

            if saved_answer == NO_MATCH_ANSWER:
                flash(
                    "LifeOS could not find enough document evidence "
                    "to answer that question.",
                    "warning",
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
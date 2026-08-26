from __future__ import annotations

from collections import Counter
import json

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_login import current_user

from lifeos.api.v1.common import api_auth_required, json_body, not_found, persistence_error, validation_error
from lifeos.api.v1.serializers import (
    json_safe,
    serialize_document,
    serialize_document_analysis,
    serialize_document_comparison,
    serialize_document_question,
    serialize_document_ocr_status,
    serialize_document_suggestion,
    serialize_document_summary,
    serialize_project_summary,
    serialize_task,
    serialize_version_history,
)
from models import DocumentAIAnalysis
from services.document_access_service import DocumentNotFoundError as AccessDocumentNotFoundError, DocumentPersistenceError, DocumentValidationError, list_owned_documents, require_owned_document
from services.document_ai_workflow_service import DocumentAnalysisWorkflowError, DocumentNotFoundError, DocumentNotReadyError, analyse_owned_document
from services.document_analysis_experience_service import build_document_analysis_experience
from services.document_comparison_service import DocumentComparisonNotFoundError, DocumentComparisonValidationError, list_owned_comparisons, require_owned_comparison
from services.document_comparison_workflow_service import DocumentComparisonPersistenceError, DocumentComparisonWorkflowError, compare_owned_documents
from services.document_navigation_service import (
    DocumentNavigationError,
    DocumentNavigationNotFoundError,
    DocumentNavigationNotReadyError,
    DocumentNavigationValidationError,
    get_owned_document_context,
    prepare_owned_document_file,
)
from services.document_overview_service import build_structured_document_overview
from services.document_ocr_workflow_service import (
    DocumentOCRNotFoundError,
    DocumentOCRWorkflowError,
    queue_owned_document_ocr,
)
from services.document_question_workflow_service import DocumentQuestionNotFoundError, DocumentQuestionNotReadyError, DocumentQuestionWorkflowError, ask_owned_document, list_owned_document_questions
from services.document_search_service import (
    DocumentSearchError,
    DocumentSearchNotFoundError,
    DocumentSearchNotReadyError,
    DocumentSearchValidationError,
    search_owned_document,
)
from services.document_pdf_search_service import (
    DocumentPDFSearchError,
    DocumentPDFSearchNotFoundError,
    DocumentPDFSearchNotReadyError,
    DocumentPDFSearchValidationError,
    search_owned_document_for_pdf,
)
from services.document_service import DocumentUploadError, create_project_pdf_document
from services.document_task_action_service import (
    DocumentSuggestionDuplicateError,
    DocumentSuggestionNotFoundError,
    DocumentSuggestionPersistenceError,
    DocumentSuggestionWorkflowError,
    approve_document_suggestion,
    link_suggestion_to_existing_task,
    list_document_suggestions,
    reject_document_suggestion,
    require_owned_document_suggestion,
)
from services.document_type_detection_workflow_service import DocumentTypeDetectionNotFoundError, DocumentTypeDetectionNotReadyError, DocumentTypeDetectionWorkflowError, detect_owned_document_type
from services.document_type_profile_service import document_type_choices
from services.document_type_workspace_service import build_document_type_workspace
from services.document_version_service import DocumentVersionNotFoundError, DocumentVersionPersistenceError, DocumentVersionValidationError, create_new_document_version, get_owned_document_version_history
from services.pdf_service import PDFValidationError
from services.project_service import list_owned_projects
from storage.base import StorageError
from storage.service import get_storage


documents_api_bp = Blueprint("api_v1_documents", __name__, url_prefix="/api/v1/documents")


def _max_upload_bytes():
    return int(current_app.config.get("MAX_CONTENT_LENGTH") or 25 * 1024 * 1024)


def _details(document):
    analysis_query = DocumentAIAnalysis.query.filter_by(document_id=document.id, user_id=current_user.id)
    if document.is_historical_version:
        analysis_query = analysis_query.filter(DocumentAIAnalysis.status.in_(["Outdated", "Historical", "Completed"]))
    else:
        analysis_query = analysis_query.filter_by(status="Completed")
    latest_analysis = analysis_query.order_by(DocumentAIAnalysis.created_at.desc(), DocumentAIAnalysis.id.desc()).first()
    latest_attempt = DocumentAIAnalysis.query.filter_by(document_id=document.id, user_id=current_user.id).order_by(DocumentAIAnalysis.created_at.desc(), DocumentAIAnalysis.id.desc()).first()
    try:
        version_history = get_owned_document_version_history(document_id=document.id, owner_id=current_user.id)
    except DocumentVersionNotFoundError:
        version_history = None
    try:
        suggestions = list_document_suggestions(document_id=document.id, user_id=current_user.id)
    except DocumentSuggestionNotFoundError:
        suggestions = []
    overview = build_structured_document_overview(latest_analysis)
    type_workspace = build_document_type_workspace(latest_analysis)
    analysis_experience = build_document_analysis_experience(overview=overview, type_workspace=type_workspace, suggestions=suggestions)
    questions = list_owned_document_questions(document_id=document.id, user_id=current_user.id, limit=50)
    return {
        "document": serialize_document(document),
        "analysis": serialize_document_analysis(latest_analysis),
        "latest_attempt": serialize_document_analysis(latest_attempt),
        "overview": json_safe(overview),
        "type_workspace": json_safe(type_workspace),
        "analysis_experience": json_safe(analysis_experience),
        "suggestions": [serialize_document_suggestion(x) for x in suggestions],
        "question_history": [serialize_document_question(x) for x in questions],
        "document_type_choices": [{"key": key, "label": label} for key, label in document_type_choices()],
        "version_history": serialize_version_history(version_history),
        "pdf_url": f"/api/v1/documents/{document.id}/file",
    }


@documents_api_bp.get("")
@api_auth_required
def documents():
    rows = [row for row in list_owned_documents(current_user.id) if row.is_current_version]
    return jsonify({
        "items": [serialize_document(row) for row in rows],
        "projects": [serialize_project_summary(x) for x in list_owned_projects(current_user.id)],
        "max_upload_bytes": _max_upload_bytes(),
    })


@documents_api_bp.post("")
@api_auth_required
def upload_document_route():
    raw_project_id = str(request.form.get("project_id") or "").strip()
    try:
        project_id = int(raw_project_id)
    except (TypeError, ValueError):
        return validation_error("Please select a valid project.")
    try:
        result = create_project_pdf_document(request.files.get("document"), owner_id=current_user.id, project_id=project_id, max_bytes=_max_upload_bytes())
    except (PDFValidationError, DocumentValidationError) as error:
        return validation_error(str(error))
    except (DocumentPersistenceError, DocumentUploadError, StorageError):
        current_app.logger.exception("API document upload failed")
        return persistence_error("LifeOS could not save the document.")
    ocr_job_id = None
    if (
        current_app.config.get("OCR_AUTO_ENQUEUE")
        and result.document.ocr_status == "pending"
    ):
        try:
            queued_ocr = queue_owned_document_ocr(
                document_id=result.document.id,
                user_id=current_user.id,
            )
            result_document = queued_ocr.document
            ocr_job_id = queued_ocr.job_id
        except DocumentOCRWorkflowError:
            current_app.logger.exception(
                "Automatic OCR queueing failed for document %s.",
                result.document.id,
            )
            result_document = result.document
    else:
        result_document = result.document

    return jsonify({
        "item": serialize_document(result_document),
        "extraction_succeeded": result.extraction_succeeded,
        "pages_with_text": result.pages_with_text,
        "indexing_succeeded": result.indexing_succeeded,
        "chunk_count": result.chunk_count,
        "indexing_message": result.indexing_message,
        "ocr_job_id": ocr_job_id,
    }), 201


@documents_api_bp.get("/<int:document_id>")
@api_auth_required
def document_details_route(document_id: int):
    try:
        document = require_owned_document(document_id, current_user.id)
    except AccessDocumentNotFoundError:
        return not_found("Document not found.")
    return jsonify(_details(document))


@documents_api_bp.get("/<int:document_id>/ocr")
@api_auth_required
def document_ocr_status_route(document_id: int):
    try:
        document = require_owned_document(document_id, current_user.id)
    except AccessDocumentNotFoundError:
        return not_found("Document not found.")
    return jsonify({"ocr": serialize_document_ocr_status(document)})


@documents_api_bp.get("/<int:document_id>/ocr/layout")
@api_auth_required
def document_ocr_layout_route(document_id: int):
    try:
        document = require_owned_document(document_id, current_user.id)
    except AccessDocumentNotFoundError:
        return not_found("Document not found.")

    try:
        page_number = int(request.args.get("page") or 0)
    except (TypeError, ValueError):
        page_number = 0

    if page_number <= 0:
        return validation_error("Please provide a valid PDF page number.")

    raw_layout = str(getattr(document, "ocr_layout_json", "") or "").strip()
    if not raw_layout:
        return jsonify({
            "status": str(getattr(document, "ocr_status", "not_needed") or "not_needed"),
            "layout_available": False,
            "page": page_number,
            "source": "native",
            "text": "",
            "words": [],
        })

    try:
        payload = json.loads(raw_layout)
    except (TypeError, ValueError, json.JSONDecodeError):
        current_app.logger.warning(
            "Invalid OCR layout JSON for document %s.", document_id
        )
        return persistence_error("LifeOS could not read the OCR text layer.")

    pages = payload.get("pages") if isinstance(payload, dict) else {}
    page = pages.get(str(page_number), {}) if isinstance(pages, dict) else {}
    if not isinstance(page, dict):
        page = {}

    words = page.get("words") if isinstance(page.get("words"), list) else []
    return jsonify({
        "status": str(getattr(document, "ocr_status", "not_needed") or "not_needed"),
        "layout_available": True,
        "page": page_number,
        "source": str(page.get("source") or "native"),
        "confidence": page.get("confidence"),
        "text": str(page.get("text") or ""),
        "words": words,
    })


@documents_api_bp.post("/<int:document_id>/ocr")
@api_auth_required
def document_ocr_start_route(document_id: int):
    payload = json_body()
    force = bool(payload.get("force", False))
    try:
        result = queue_owned_document_ocr(
            document_id=document_id,
            user_id=current_user.id,
            force=force,
        )
    except DocumentOCRNotFoundError:
        return not_found("Document not found.")
    except DocumentOCRWorkflowError as error:
        current_app.logger.exception(
            "API OCR start failed for document %s.", document_id
        )
        return jsonify({
            "error": "ocr_failed",
            "message": str(error),
        }), 503

    return jsonify({
        "ocr": serialize_document_ocr_status(result.document),
        "job_id": result.job_id,
        "queued": result.queued,
    }), 202


@documents_api_bp.get("/<int:document_id>/search")
@api_auth_required
def search_document_api(document_id: int):
    query = str(request.args.get("q") or "")
    try:
        result = search_owned_document(
            document_id=document_id,
            user_id=current_user.id,
            query=query,
        )
    except DocumentSearchNotFoundError:
        return not_found("Document not found.")
    except (DocumentSearchNotReadyError, DocumentSearchValidationError) as error:
        return validation_error(str(error))
    except DocumentSearchError as error:
        current_app.logger.exception("API document search failed for document %s.", document_id)
        return jsonify({"error": "search_failed", "message": str(error)}), 503

    return jsonify({
        "query": result.query,
        "mode": result.mode,
        "result_count": result.result_count,
        "semantic_fallback": result.semantic_fallback,
        "items": [
            {
                "rank": hit.rank,
                "chunk_id": hit.chunk_id,
                "chunk_index": hit.chunk_index,
                "page_start": hit.page_start,
                "page_end": hit.page_end,
                "page_label": hit.page_label,
                "section": hit.section,
                "preview": hit.preview,
                "exact_phrase": hit.exact_phrase,
                "method_label": hit.method_label,
                "match_strength": hit.match_strength,
            }
            for hit in result.hits
        ],
    })


@documents_api_bp.get("/<int:document_id>/semantic-search")
@api_auth_required
def semantic_search_document_api(document_id: int):
    query = str(request.args.get("q") or "")
    try:
        result = search_owned_document_for_pdf(
            document_id=document_id,
            user_id=current_user.id,
            query=query,
        )
    except DocumentPDFSearchNotFoundError:
        return not_found("Document not found.")
    except (DocumentPDFSearchNotReadyError, DocumentPDFSearchValidationError) as error:
        return validation_error(str(error))
    except DocumentPDFSearchError:
        current_app.logger.exception("API semantic PDF search failed for document %s.", document_id)
        return persistence_error("LifeOS could not search this PDF right now.")
    return jsonify(result.as_dict())


@documents_api_bp.get("/<int:document_id>/context/<int:chunk_id>")
@api_auth_required
def document_context_api(document_id: int, chunk_id: int):
    try:
        result = get_owned_document_context(
            document_id=document_id,
            user_id=current_user.id,
            chunk_id=chunk_id,
        )
    except DocumentNavigationNotFoundError:
        return not_found("Document source not found.")
    except (DocumentNavigationNotReadyError, DocumentNavigationValidationError) as error:
        return validation_error(str(error))
    except DocumentNavigationError:
        return persistence_error("LifeOS could not open this source context.")
    return jsonify(result.as_dict())


@documents_api_bp.get("/<int:document_id>/file")
@api_auth_required
def document_file_route(document_id: int):
    try:
        info = prepare_owned_document_file(document_id=document_id, user_id=current_user.id)
    except (DocumentNavigationNotFoundError, DocumentNavigationValidationError, DocumentNavigationNotReadyError):
        return not_found("Document file not found.")
    except DocumentNavigationError:
        return persistence_error("LifeOS could not open the document file.")
    download = request.args.get("download") == "1"
    try:
        if info.local_path is not None:
            response = send_file(info.local_path, mimetype="application/pdf", as_attachment=download, download_name=info.filename, conditional=True)
        else:
            response = send_file(get_storage().open(info.storage_key, "rb"), mimetype="application/pdf", as_attachment=download, download_name=info.filename, conditional=False)
    except StorageError:
        return persistence_error("LifeOS could not open the document file.")
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    # Allow the separated React frontend to embed this same-origin PDF in its viewer.
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


@documents_api_bp.post("/<int:document_id>/detect-type")
@api_auth_required
def detect_type_route(document_id: int):
    try:
        result = detect_owned_document_type(document_id=document_id, user_id=current_user.id)
    except DocumentTypeDetectionNotFoundError:
        return not_found("Document not found.")
    except DocumentTypeDetectionNotReadyError as error:
        return validation_error(str(error))
    except DocumentTypeDetectionWorkflowError as error:
        return jsonify({"error": "ai_unavailable", "message": str(error)}), 503
    d = result.detection
    return jsonify({"detection": {"document_type_key": d.document_type_key, "document_type_label": d.document_type_label, "confidence": d.confidence, "reason": d.reason}})


@documents_api_bp.post("/<int:document_id>/analyze")
@api_auth_required
def analyze_route(document_id: int):
    payload = json_body()
    try:
        result = analyse_owned_document(
            document_id=document_id,
            user_id=current_user.id,
            force=bool(payload.get("force")),
            confirmed_document_type=payload.get("confirmed_document_type"),
            detected_document_type=payload.get("detected_document_type"),
            detection_confidence=payload.get("detection_confidence"),
        )
    except DocumentNotFoundError:
        return not_found("Document not found.")
    except DocumentNotReadyError as error:
        return validation_error(str(error))
    except DocumentAnalysisWorkflowError as error:
        return jsonify({"error": "analysis_failed", "message": str(error)}), 503
    return jsonify({"analysis": serialize_document_analysis(result.analysis), "reused_existing": result.reused_existing, **_details(result.document)})


@documents_api_bp.post("/<int:document_id>/questions")
@api_auth_required
def ask_document_route(document_id: int):
    payload = json_body()
    try:
        result = ask_owned_document(
            document_id=document_id,
            user_id=current_user.id,
            question_text=payload.get("question"),
            force=bool(payload.get("force")),
            selected_context_text=str(payload.get("selected_context_text") or ""),
            selected_context_page=payload.get("selected_context_page"),
            selected_context_section=str(payload.get("selected_context_section") or ""),
        )
    except DocumentQuestionNotFoundError:
        return not_found("Document not found.")
    except DocumentQuestionNotReadyError as error:
        return validation_error(str(error))
    except DocumentQuestionWorkflowError as error:
        return jsonify({"error": "question_failed", "message": str(error)}), 503
    return jsonify({"item": serialize_document_question(result.question), "reused_existing": result.reused_existing})


@documents_api_bp.post("/<int:document_id>/versions")
@api_auth_required
def new_version_route(document_id: int):
    try:
        result = create_new_document_version(request.files.get("document"), source_document_id=document_id, owner_id=current_user.id, max_bytes=_max_upload_bytes())
    except DocumentVersionNotFoundError:
        return not_found("Document not found.")
    except (DocumentVersionValidationError, PDFValidationError) as error:
        return validation_error(str(error))
    except (DocumentVersionPersistenceError, StorageError):
        return persistence_error("LifeOS could not save the new document version.")
    return jsonify({
        "item": serialize_document(result.current_document),
        "previous": serialize_document(result.previous_document),
        "change_summary": json_safe(result.change_summary),
        "outdated": {
            "analyses": result.outdated_analyses,
            "questions": result.outdated_questions,
            "suggestions": result.outdated_suggestions,
            "project_questions": result.outdated_project_questions,
        },
    }), 201


@documents_api_bp.get("/comparisons")
@api_auth_required
def comparisons_route():
    return jsonify({
        "documents": [serialize_document_summary(x) for x in list_owned_documents(current_user.id) if x.is_current_version],
        "items": [serialize_document_comparison(x) for x in list_owned_comparisons(owner_id=current_user.id, limit=50)],
    })


@documents_api_bp.post("/comparisons")
@api_auth_required
def create_comparison_route():
    payload = json_body()
    try:
        result = compare_owned_documents(owner_id=current_user.id, document_a_id=payload.get("document_a_id"), document_b_id=payload.get("document_b_id"), force=bool(payload.get("force")))
    except DocumentComparisonValidationError as error:
        return validation_error(str(error))
    except DocumentComparisonNotFoundError:
        return not_found("Document not found.")
    except (DocumentComparisonPersistenceError, DocumentComparisonWorkflowError) as error:
        return jsonify({"error": "comparison_failed", "message": str(error)}), 503
    return jsonify({"item": serialize_document_comparison(result.comparison), "reused_existing": result.reused_existing, "rejected_findings": result.rejected_findings})


@documents_api_bp.get("/comparisons/<int:comparison_id>")
@api_auth_required
def comparison_details_route(comparison_id: int):
    try:
        comparison = require_owned_comparison(comparison_id=comparison_id, owner_id=current_user.id)
    except DocumentComparisonNotFoundError:
        return not_found("Comparison not found.")
    counts = Counter(str(item.get("category") or "Other") for item in comparison.findings if isinstance(item, dict))
    return jsonify({"item": serialize_document_comparison(comparison), "category_counts": dict(counts)})


@documents_api_bp.post("/comparisons/<int:comparison_id>/rerun")
@api_auth_required
def rerun_comparison_route(comparison_id: int):
    try:
        comparison = require_owned_comparison(comparison_id=comparison_id, owner_id=current_user.id)
        result = compare_owned_documents(owner_id=current_user.id, document_a_id=comparison.document_a_id, document_b_id=comparison.document_b_id, force=True)
    except DocumentComparisonNotFoundError:
        return not_found("Comparison not found.")
    except (DocumentComparisonPersistenceError, DocumentComparisonWorkflowError, DocumentComparisonValidationError) as error:
        return jsonify({"error": "comparison_failed", "message": str(error)}), 503
    return jsonify({"item": serialize_document_comparison(result.comparison), "rejected_findings": result.rejected_findings})


@documents_api_bp.post("/<int:document_id>/suggestions/<int:suggestion_id>/approve")
@api_auth_required
def approve_suggestion_route(document_id: int, suggestion_id: int):
    payload = json_body()
    try:
        suggestion = require_owned_document_suggestion(document_id=document_id, suggestion_id=suggestion_id, user_id=current_user.id)
        task = approve_document_suggestion(suggestion=suggestion, user_id=current_user.id, allow_possible_duplicate=bool(payload.get("allow_possible_duplicate")))
    except DocumentSuggestionNotFoundError:
        return not_found("Suggestion not found.")
    except (DocumentSuggestionDuplicateError, DocumentSuggestionWorkflowError) as error:
        return validation_error(str(error))
    except DocumentSuggestionPersistenceError as error:
        return persistence_error(str(error))
    return jsonify({"task": serialize_task(task)})


@documents_api_bp.post("/<int:document_id>/suggestions/<int:suggestion_id>/link")
@api_auth_required
def link_suggestion_route(document_id: int, suggestion_id: int):
    try:
        suggestion = require_owned_document_suggestion(document_id=document_id, suggestion_id=suggestion_id, user_id=current_user.id)
        task = link_suggestion_to_existing_task(suggestion=suggestion, user_id=current_user.id)
    except DocumentSuggestionNotFoundError:
        return not_found("Suggestion not found.")
    except DocumentSuggestionWorkflowError as error:
        return validation_error(str(error))
    except DocumentSuggestionPersistenceError as error:
        return persistence_error(str(error))
    return jsonify({"task": serialize_task(task)})


@documents_api_bp.post("/<int:document_id>/suggestions/<int:suggestion_id>/reject")
@api_auth_required
def reject_suggestion_route(document_id: int, suggestion_id: int):
    try:
        suggestion = require_owned_document_suggestion(document_id=document_id, suggestion_id=suggestion_id, user_id=current_user.id)
        status = reject_document_suggestion(suggestion)
    except DocumentSuggestionNotFoundError:
        return not_found("Suggestion not found.")
    except DocumentSuggestionWorkflowError as error:
        return validation_error(str(error))
    except DocumentSuggestionPersistenceError as error:
        return persistence_error(str(error))
    return jsonify({"status": status})

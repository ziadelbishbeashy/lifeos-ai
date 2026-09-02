"""React API for Modules V1 knowledge workspaces."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user

from lifeos.api.v1.common import (
    api_auth_required,
    json_body,
    not_found,
    persistence_error,
    validation_error,
)
from lifeos.api.v1.serializers import (
    serialize_document_collection,
    serialize_document_summary,
    serialize_module,
    serialize_module_assessment,
    serialize_module_question,
    serialize_note_summary,
    serialize_task,
)
from models import Note, Task
from services.document_access_service import list_owned_documents
from services.document_collection_service import list_owned_collections
from services.document_ocr_workflow_service import DocumentOCRWorkflowError, queue_owned_document_ocr
from services.document_service import DocumentUploadError
from services.module_assessment_service import (
    ModuleAssessmentNotFoundError,
    ModuleAssessmentPersistenceError,
    ModuleAssessmentValidationError,
    create_owned_module_assessment,
    delete_owned_module_assessment,
    list_owned_module_assessments,
    update_owned_module_assessment,
)
from services.module_question_workflow_service import (
    ModuleQuestionNotFoundError,
    ModuleQuestionNotReadyError,
    ModuleQuestionWorkflowError,
    ask_owned_module_documents,
    list_owned_module_questions,
)
from services.module_service import (
    ModuleNotFoundError,
    ModulePersistenceError,
    ModuleValidationError,
    create_lecture,
    create_module,
    delete_lecture,
    delete_module,
    link_collection,
    link_document,
    link_note,
    link_task,
    list_owned_modules,
    require_owned_module,
    unlink_collection,
    unlink_document,
    unlink_note,
    unlink_task,
    update_lecture,
    update_module,
    upload_module_document,
)
from services.pdf_service import PDFValidationError
from services.document_access_service import DocumentPersistenceError, DocumentValidationError
from storage.base import StorageError


modules_api_bp = Blueprint("api_v1_modules", __name__, url_prefix="/api/v1/modules")


def _max_upload_bytes() -> int:
    return int(current_app.config.get("MAX_CONTENT_LENGTH") or 25 * 1024 * 1024)


def _int_or_none(value):
    if value in (None, "", 0, "0"):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ModuleValidationError("Select a valid lecture.") from error
    if parsed <= 0:
        raise ModuleValidationError("Select a valid lecture.")
    return parsed


def _detail_payload(module):
    module_questions = list_owned_module_questions(
        module_id=module.id,
        user_id=current_user.id,
        limit=50,
    )
    lecture_questions = {}
    for lecture in module.lectures:
        lecture_questions[str(lecture.id)] = [
            serialize_module_question(item)
            for item in list_owned_module_questions(
                module_id=module.id,
                lecture_id=lecture.id,
                user_id=current_user.id,
                limit=50,
            )
        ]

    return {
        "item": serialize_module(module, include_resources=True),
        "question_history": [serialize_module_question(item) for item in module_questions],
        "lecture_question_history": lecture_questions,
        "available": {
            "documents": [
                serialize_document_summary(item)
                for item in list_owned_documents(current_user.id)
                if bool(item.is_current_version)
            ],
            "notes": [
                serialize_note_summary(item)
                for item in Note.query.filter_by(user_id=current_user.id)
                .order_by(Note.updated_at.desc(), Note.id.desc())
                .all()
            ],
            "tasks": [
                serialize_task(item)
                for item in Task.query.filter_by(user_id=current_user.id)
                .order_by(Task.created_at.desc(), Task.id.desc())
                .all()
            ],
            "collections": [
                serialize_document_collection(item)
                for item in list_owned_collections(current_user.id)
            ],
        },
        "max_upload_bytes": _max_upload_bytes(),
    }


@modules_api_bp.get("")
@api_auth_required
def list_modules_route():
    rows = list_owned_modules(current_user.id)
    return jsonify({"items": [serialize_module(item) for item in rows]})


@modules_api_bp.post("")
@api_auth_required
def create_module_route():
    payload = json_body()
    try:
        module = create_module(
            user_id=current_user.id,
            title=payload.get("title"),
            description=payload.get("description"),
            subject=payload.get("subject"),
            status=payload.get("status", "Active"),
        )
    except ModuleValidationError as error:
        return validation_error(str(error))
    except ModulePersistenceError:
        current_app.logger.exception("LifeOS API could not create a module.")
        return persistence_error("The module could not be created.")
    return jsonify({"item": serialize_module(module, include_resources=True)}), 201


@modules_api_bp.get("/<int:module_id>")
@api_auth_required
def module_details_route(module_id: int):
    try:
        module = require_owned_module(module_id, current_user.id)
        return jsonify(_detail_payload(module))
    except (ModuleNotFoundError, ModuleQuestionNotFoundError):
        return not_found("Module not found.")


@modules_api_bp.patch("/<int:module_id>")
@api_auth_required
def update_module_route(module_id: int):
    payload = json_body()
    try:
        module = update_module(
            module_id=module_id,
            user_id=current_user.id,
            title=payload.get("title"),
            description=payload.get("description"),
            subject=payload.get("subject"),
            status=payload.get("status"),
            provided_fields=set(payload.keys()),
        )
    except ModuleNotFoundError:
        return not_found("Module not found.")
    except ModuleValidationError as error:
        return validation_error(str(error))
    except ModulePersistenceError:
        return persistence_error("The module could not be updated.")
    return jsonify({"item": serialize_module(module, include_resources=True)})


@modules_api_bp.delete("/<int:module_id>")
@api_auth_required
def delete_module_route(module_id: int):
    try:
        title = delete_module(module_id=module_id, user_id=current_user.id)
    except ModuleNotFoundError:
        return not_found("Module not found.")
    except ModulePersistenceError:
        return persistence_error("The module could not be deleted.")
    return jsonify({"deleted": True, "title": title})


@modules_api_bp.get("/<int:module_id>/assessments")
@api_auth_required
def list_module_assessments_route(module_id: int):
    try:
        rows = list_owned_module_assessments(
            module_id=module_id,
            user_id=current_user.id,
        )
    except ModuleNotFoundError:
        return not_found("Module not found.")
    return jsonify({"items": [serialize_module_assessment(item) for item in rows]})


@modules_api_bp.post("/<int:module_id>/assessments")
@api_auth_required
def create_module_assessment_route(module_id: int):
    payload = json_body()
    try:
        assessment = create_owned_module_assessment(
            module_id=module_id,
            user_id=current_user.id,
            title=payload.get("title"),
            assessment_type=payload.get("assessment_type"),
            assessment_date=payload.get("assessment_date"),
            assessment_time=payload.get("assessment_time"),
            due_date=payload.get("due_date"),
            due_time=payload.get("due_time"),
            weight_percent=payload.get("weight_percent"),
            status=payload.get("status", "Upcoming"),
            topics=payload.get("topics"),
            estimated_study_minutes=payload.get("estimated_study_minutes"),
            notes=payload.get("notes"),
        )
    except ModuleNotFoundError:
        return not_found("Module not found.")
    except ModuleAssessmentValidationError as error:
        return validation_error(str(error))
    except ModuleAssessmentPersistenceError:
        current_app.logger.exception("LifeOS API could not create an assessment.")
        return persistence_error("The assessment could not be created.")
    return jsonify({"item": serialize_module_assessment(assessment)}), 201


@modules_api_bp.patch("/<int:module_id>/assessments/<int:assessment_id>")
@api_auth_required
def update_module_assessment_route(module_id: int, assessment_id: int):
    try:
        assessment = update_owned_module_assessment(
            assessment_id=assessment_id,
            user_id=current_user.id,
            module_id=module_id,
            changes=json_body(),
        )
    except ModuleAssessmentNotFoundError:
        return not_found("Assessment not found.")
    except ModuleAssessmentValidationError as error:
        return validation_error(str(error))
    except ModuleAssessmentPersistenceError:
        current_app.logger.exception("LifeOS API could not update an assessment.")
        return persistence_error("The assessment could not be updated.")
    return jsonify({"item": serialize_module_assessment(assessment)})


@modules_api_bp.delete("/<int:module_id>/assessments/<int:assessment_id>")
@api_auth_required
def delete_module_assessment_route(module_id: int, assessment_id: int):
    try:
        title = delete_owned_module_assessment(
            assessment_id=assessment_id,
            user_id=current_user.id,
            module_id=module_id,
        )
    except ModuleAssessmentNotFoundError:
        return not_found("Assessment not found.")
    except ModuleAssessmentPersistenceError:
        current_app.logger.exception("LifeOS API could not delete an assessment.")
        return persistence_error("The assessment could not be deleted.")
    return jsonify({"deleted": True, "title": title})


@modules_api_bp.post("/<int:module_id>/lectures")
@api_auth_required
def create_lecture_route(module_id: int):
    payload = json_body()
    try:
        create_lecture(
            module_id=module_id,
            user_id=current_user.id,
            title=payload.get("title"),
            lecture_number=payload.get("lecture_number"),
            lecture_date=payload.get("lecture_date"),
            status=payload.get("status", "Planned"),
            topics=payload.get("topics"),
            summary=payload.get("summary"),
        )
        module = require_owned_module(module_id, current_user.id)
    except ModuleNotFoundError:
        return not_found("Module not found.")
    except ModuleValidationError as error:
        return validation_error(str(error))
    except ModulePersistenceError:
        return persistence_error("The lecture could not be created.")
    return jsonify({"item": serialize_module(module, include_resources=True)}), 201


@modules_api_bp.patch("/<int:module_id>/lectures/<int:lecture_id>")
@api_auth_required
def update_lecture_route(module_id: int, lecture_id: int):
    try:
        update_lecture(
            module_id=module_id,
            lecture_id=lecture_id,
            user_id=current_user.id,
            payload=json_body(),
        )
        module = require_owned_module(module_id, current_user.id)
    except ModuleNotFoundError:
        return not_found("Lecture not found.")
    except ModuleValidationError as error:
        return validation_error(str(error))
    except ModulePersistenceError:
        return persistence_error("The lecture could not be updated.")
    return jsonify({"item": serialize_module(module, include_resources=True)})


@modules_api_bp.delete("/<int:module_id>/lectures/<int:lecture_id>")
@api_auth_required
def delete_lecture_route(module_id: int, lecture_id: int):
    try:
        title = delete_lecture(module_id=module_id, lecture_id=lecture_id, user_id=current_user.id)
        module = require_owned_module(module_id, current_user.id)
    except ModuleNotFoundError:
        return not_found("Lecture not found.")
    except ModulePersistenceError:
        return persistence_error("The lecture could not be deleted.")
    return jsonify({"deleted": True, "title": title, "item": serialize_module(module, include_resources=True)})


@modules_api_bp.post("/<int:module_id>/documents")
@api_auth_required
def link_document_route(module_id: int):
    payload = json_body()
    try:
        document_id = int(payload.get("document_id"))
        lecture_id = _int_or_none(payload.get("lecture_id"))
        link_document(
            module_id=module_id,
            document_id=document_id,
            user_id=current_user.id,
            lecture_id=lecture_id,
        )
        module = require_owned_module(module_id, current_user.id)
    except (TypeError, ValueError):
        return validation_error("Select a valid document.")
    except ModuleNotFoundError as error:
        return not_found(str(error))
    except ModuleValidationError as error:
        return validation_error(str(error))
    except ModulePersistenceError:
        return persistence_error("The document could not be linked to the module.")
    return jsonify({"item": serialize_module(module, include_resources=True)})


@modules_api_bp.post("/<int:module_id>/documents/upload")
@api_auth_required
def upload_document_route(module_id: int):
    try:
        lecture_id = _int_or_none(request.form.get("lecture_id"))
        result = upload_module_document(
            request.files.get("document"),
            module_id=module_id,
            user_id=current_user.id,
            lecture_id=lecture_id,
            max_bytes=_max_upload_bytes(),
        )
    except ModuleNotFoundError as error:
        return not_found(str(error))
    except (PDFValidationError, DocumentValidationError, ModuleValidationError) as error:
        return validation_error(str(error))
    except (DocumentPersistenceError, DocumentUploadError, ModulePersistenceError, StorageError):
        current_app.logger.exception("Module document upload failed")
        return persistence_error("LifeOS could not save the module document.")

    document = result.upload.document
    ocr_job_id = None
    if current_app.config.get("OCR_AUTO_ENQUEUE") and document.ocr_status == "pending":
        try:
            queued = queue_owned_document_ocr(document_id=document.id, user_id=current_user.id)
            document = queued.document
            ocr_job_id = queued.job_id
        except DocumentOCRWorkflowError:
            current_app.logger.exception("Automatic OCR queueing failed for module document %s.", document.id)

    module = require_owned_module(module_id, current_user.id)
    return jsonify({
        "item": serialize_module(module, include_resources=True),
        "document": serialize_document_summary(document),
        "extraction_succeeded": result.upload.extraction_succeeded,
        "indexing_succeeded": result.upload.indexing_succeeded,
        "chunk_count": result.upload.chunk_count,
        "table_count": result.upload.table_count,
        "ocr_job_id": ocr_job_id,
    }), 201


@modules_api_bp.delete("/<int:module_id>/documents/<int:document_id>")
@api_auth_required
def unlink_document_route(module_id: int, document_id: int):
    try:
        unlink_document(module_id=module_id, document_id=document_id, user_id=current_user.id)
        module = require_owned_module(module_id, current_user.id)
    except ModuleNotFoundError as error:
        return not_found(str(error))
    except ModulePersistenceError:
        return persistence_error("The document could not be removed from the module.")
    return jsonify({"removed": True, "item": serialize_module(module, include_resources=True)})


def _resource_link_route(module_id: int, kind: str):
    payload = json_body()
    key = f"{kind}_id"
    try:
        resource_id = int(payload.get(key))
        lecture_id = _int_or_none(payload.get("lecture_id")) if kind in {"note", "task"} else None
        if kind == "note":
            link_note(module_id=module_id, note_id=resource_id, user_id=current_user.id, lecture_id=lecture_id)
        elif kind == "task":
            link_task(module_id=module_id, task_id=resource_id, user_id=current_user.id, lecture_id=lecture_id)
        else:
            link_collection(module_id=module_id, collection_id=resource_id, user_id=current_user.id)
        module = require_owned_module(module_id, current_user.id)
    except (TypeError, ValueError):
        return validation_error(f"Select a valid {kind}.")
    except ModuleNotFoundError as error:
        return not_found(str(error))
    except ModuleValidationError as error:
        return validation_error(str(error))
    except ModulePersistenceError:
        return persistence_error(f"The {kind} could not be linked to the module.")
    return jsonify({"item": serialize_module(module, include_resources=True)})


def _resource_unlink_route(module_id: int, kind: str, resource_id: int):
    try:
        if kind == "note":
            unlink_note(module_id=module_id, note_id=resource_id, user_id=current_user.id)
        elif kind == "task":
            unlink_task(module_id=module_id, task_id=resource_id, user_id=current_user.id)
        else:
            unlink_collection(module_id=module_id, collection_id=resource_id, user_id=current_user.id)
        module = require_owned_module(module_id, current_user.id)
    except ModuleNotFoundError as error:
        return not_found(str(error))
    except ModulePersistenceError:
        return persistence_error(f"The {kind} could not be removed from the module.")
    return jsonify({"removed": True, "item": serialize_module(module, include_resources=True)})


@modules_api_bp.post("/<int:module_id>/notes")
@api_auth_required
def link_note_route(module_id: int):
    return _resource_link_route(module_id, "note")


@modules_api_bp.delete("/<int:module_id>/notes/<int:note_id>")
@api_auth_required
def unlink_note_route(module_id: int, note_id: int):
    return _resource_unlink_route(module_id, "note", note_id)


@modules_api_bp.post("/<int:module_id>/tasks")
@api_auth_required
def link_task_route(module_id: int):
    return _resource_link_route(module_id, "task")


@modules_api_bp.delete("/<int:module_id>/tasks/<int:task_id>")
@api_auth_required
def unlink_task_route(module_id: int, task_id: int):
    return _resource_unlink_route(module_id, "task", task_id)


@modules_api_bp.post("/<int:module_id>/collections")
@api_auth_required
def link_collection_route(module_id: int):
    return _resource_link_route(module_id, "collection")


@modules_api_bp.delete("/<int:module_id>/collections/<int:collection_id>")
@api_auth_required
def unlink_collection_route(module_id: int, collection_id: int):
    return _resource_unlink_route(module_id, "collection", collection_id)


@modules_api_bp.post("/<int:module_id>/questions")
@api_auth_required
def ask_module_route(module_id: int):
    payload = json_body()
    try:
        lecture_id = _int_or_none(payload.get("lecture_id"))
        result = ask_owned_module_documents(
            module_id=module_id,
            lecture_id=lecture_id,
            user_id=current_user.id,
            question_text=payload.get("question"),
            force=bool(payload.get("force")),
        )
    except ModuleQuestionNotFoundError:
        return not_found("Module or lecture not found.")
    except ModuleQuestionNotReadyError as error:
        return validation_error(str(error))
    except (ModuleQuestionWorkflowError, ModuleValidationError) as error:
        return jsonify({"error": "question_failed", "message": str(error)}), 503
    return jsonify({
        "item": serialize_module_question(result.question),
        "reused_existing": result.reused_existing,
    })

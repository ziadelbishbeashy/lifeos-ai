"""React API for Projects and the Project Studio workspace."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from flask_login import current_user

from lifeos.api.v1.common import (
    api_auth_required,
    json_body,
    not_found,
    persistence_error,
    validation_error,
)
from lifeos.api.v1.serializers import (
    serialize_document_summary,
    serialize_note_summary,
    serialize_project,
    serialize_project_card,
    serialize_task,
    serialize_project_question,
    serialize_document_suggestion,
)


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
    list_owned_project_questions,
)

from lifeos.domains.projects.facade import (
    ProjectNotFoundError,
    ProjectPersistenceError,
    ProjectValidationError,
    build_project_input,
    build_project_workspace,
    build_projects_overview,
    create_project,
    delete_project,
    require_owned_project,
    update_project,
)


projects_api_bp = Blueprint(
    "api_v1_projects",
    __name__,
    url_prefix="/api/v1/projects",
)


def _project_form(project) -> dict:
    return {
        "title": project.title or "",
        "project_type": project.project_type or "",
        "description": project.description or "",
        "goal": project.goal or "",
        "tech_stack": project.tech_stack or "",
        "project_folder": project.project_folder or "",
        "github_link": project.github_link or "",
        "demo_link": project.demo_link or "",
        "start_date": project.start_date.isoformat() if project.start_date else "",
        "deadline": project.deadline.isoformat() if project.deadline else "",
        "no_deadline": "on" if project.deadline is None else "",
        "status": project.status or "In Progress",
        "priority": project.priority or "Medium",
        "current_phase": project.current_phase or "",
        "progress": project.progress or 0,
    }


def _project_input_from_json(payload: dict, project=None):
    form = _project_form(project) if project is not None else {
        "status": "In Progress",
        "priority": "Medium",
        "progress": 0,
    }
    form.update(payload)

    if isinstance(form.get("no_deadline"), bool):
        form["no_deadline"] = "on" if form["no_deadline"] else ""
    elif form.get("deadline") in (None, "") and payload.get("no_deadline") is True:
        form["no_deadline"] = "on"

    return build_project_input(form)


@projects_api_bp.get("")
@api_auth_required
def list_projects():
    overview = build_projects_overview(current_user.id)
    return jsonify(
        {
            "items": [serialize_project_card(card) for card in overview["project_cards"]],
            "counts": {
                "total": len(overview["projects"]),
                "active": overview["active_count"],
                "attention": overview["attention_count"],
                "completed": overview["completed_count"],
            },
        }
    )


@projects_api_bp.post("")
@api_auth_required
def create_project_route():
    payload = json_body()
    try:
        project = create_project(current_user.id, _project_input_from_json(payload))
    except ProjectValidationError as error:
        return validation_error(str(error))
    except ProjectPersistenceError:
        current_app.logger.exception("LifeOS API could not create a project.")
        return persistence_error("The project could not be created.")

    return jsonify({"item": serialize_project(project)}), 201


@projects_api_bp.get("/<int:project_id>")
@api_auth_required
def project_details_route(project_id: int):
    try:
        workspace = build_project_workspace(project_id, current_user.id)
    except ProjectNotFoundError:
        return not_found("Project not found.")

    current_documents = [
        document
        for document in workspace["project_documents"]
        if bool(document.is_current_version)
    ]

    return jsonify(
        {
            "project": serialize_project(workspace["project"]),
            "tasks": [serialize_task(task) for task in workspace["tasks"]],
            "recent_notes": [
                serialize_note_summary(note) for note in workspace["recent_notes"]
            ],
            "documents": [
                serialize_document_summary(document) for document in current_documents
            ],
            "metrics": {
                "total_tasks": workspace["total_tasks"],
                "completed_tasks": workspace["completed_tasks"],
                "pending_tasks": workspace["pending_tasks"],
                "in_progress_tasks": workspace["in_progress_tasks"],
                "blocked_tasks": workspace["blocked_tasks"],
                "overdue_tasks": len(workspace["overdue_tasks"]),
                "due_soon_tasks": len(workspace["due_soon_tasks"]),
                "task_progress": workspace["task_progress"],
                "notes_count": workspace["notes_count"],
                "document_count": len(current_documents),
                "searchable_document_count": sum(
                    1
                    for document in current_documents
                    if str(document.extracted_text or "").strip()
                ),
            },
            "project_health": workspace["project_health"],
            "days_to_deadline": workspace["days_to_deadline"],
            "next_task": (
                serialize_task(workspace["next_task"])
                if workspace["next_task"] is not None
                else None
            ),
            "project_question_history": [
                serialize_project_question(item)
                for item in list_owned_project_questions(
                    project_id=project_id,
                    user_id=current_user.id,
                    limit=50,
                )
            ],
            "document_suggestions": [
                serialize_document_suggestion(item)
                for item in workspace.get("document_suggestions", [])
            ],
            "pending_document_suggestion_count": workspace.get("pending_document_suggestion_count", 0),
        }
    )


@projects_api_bp.patch("/<int:project_id>")
@api_auth_required
def update_project_route(project_id: int):
    try:
        project = require_owned_project(project_id, current_user.id)
    except ProjectNotFoundError:
        return not_found("Project not found.")

    try:
        updated = update_project(
            project,
            _project_input_from_json(json_body(), project=project),
        )
    except ProjectValidationError as error:
        return validation_error(str(error))
    except ProjectPersistenceError:
        current_app.logger.exception(
            "LifeOS API could not update project %s.", project_id
        )
        return persistence_error("The project could not be updated.")

    return jsonify({"item": serialize_project(updated)})


@projects_api_bp.delete("/<int:project_id>")
@api_auth_required
def delete_project_route(project_id: int):
    try:
        project = require_owned_project(project_id, current_user.id)
    except ProjectNotFoundError:
        return not_found("Project not found.")

    try:
        title = delete_project(project)
    except ProjectPersistenceError:
        current_app.logger.exception(
            "LifeOS API could not delete project %s.", project_id
        )
        return persistence_error("The project could not be deleted.")

    return jsonify({"deleted": True, "title": title})


@projects_api_bp.post("/<int:project_id>/questions")
@api_auth_required
def ask_project_documents_route(project_id: int):
    payload = json_body()
    try:
        result = ask_owned_project_documents(
            project_id=project_id,
            user_id=current_user.id,
            question_text=payload.get("question"),
            force=bool(payload.get("force")),
        )
    except ProjectQuestionNotFoundError:
        return not_found("Project not found.")
    except ProjectQuestionNotReadyError as error:
        return validation_error(str(error))
    except ProjectQuestionWorkflowError as error:
        return jsonify({"error": "question_failed", "message": str(error)}), 503
    return jsonify({
        "item": serialize_project_question(result.question),
        "reused_existing": result.reused_existing,
    })


@projects_api_bp.get("/<int:project_id>/questions")
@api_auth_required
def project_questions_route(project_id: int):
    try:
        rows = list_owned_project_questions(
            project_id=project_id,
            user_id=current_user.id,
            limit=50,
        )
    except ProjectQuestionNotFoundError:
        return not_found("Project not found.")
    return jsonify({"items": [serialize_project_question(item) for item in rows]})


@projects_api_bp.post("/<int:project_id>/document-suggestions/bulk-create")
@api_auth_required
def bulk_create_project_document_suggestions(project_id: int):
    payload = json_body()
    try:
        require_owned_project(project_id, current_user.id)
        result = bulk_create_document_suggestions(
            suggestion_ids=payload.get("suggestion_ids") or [],
            user_id=current_user.id,
            project_id=project_id,
        )
    except ProjectNotFoundError:
        return not_found("Project not found.")
    except DocumentSuggestionNotFoundError:
        return not_found("Suggestion not found.")
    except DocumentSuggestionWorkflowError as error:
        return validation_error(str(error))
    except DocumentSuggestionPersistenceError as error:
        return persistence_error(str(error))
    return jsonify({
        "created_count": result.created_count,
        "duplicate_count": result.duplicate_count,
        "skipped_count": result.skipped_count,
        "created_tasks": [serialize_task(task) for task in result.created_tasks],
    })

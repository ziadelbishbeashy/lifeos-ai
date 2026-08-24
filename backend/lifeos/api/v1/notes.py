from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user

from lifeos.api.v1.common import api_auth_required, json_body, not_found, persistence_error, validation_error
from lifeos.api.v1.serializers import (
    serialize_note,
    serialize_note_analysis,
    serialize_note_question,
    serialize_note_suggestion,
    serialize_project_summary,
    serialize_task,
)
from services.ai_service import AIServiceError, analyze_note, ask_about_note
from services.note_service import (
    NOTE_TYPES,
    NoteNotFoundError,
    NotePersistenceError,
    NoteSuggestionNotFoundError,
    NoteValidationError,
    NoteWorkflowError,
    analysis_is_stale,
    approve_suggestion,
    build_note_details,
    build_note_input,
    build_project_context,
    create_note,
    delete_note,
    get_latest_completed_analysis,
    list_notes,
    reject_suggestion,
    require_owned_note,
    require_owned_suggestion,
    save_completed_analysis,
    save_completed_question,
    save_failed_analysis,
    save_failed_question,
    toggle_note_pin,
    update_note,
)

notes_api_bp = Blueprint("api_v1_notes", __name__, url_prefix="/api/v1/notes")


def _note_form(payload: dict, note=None):
    form = {
        "title": getattr(note, "title", ""),
        "content": getattr(note, "content", ""),
        "note_type": getattr(note, "note_type", "Quick Note"),
        "project_id": getattr(note, "project_id", "") or "",
        "is_pinned": "on" if getattr(note, "is_pinned", False) else "",
    }
    form.update(payload)
    if isinstance(form.get("is_pinned"), bool):
        form["is_pinned"] = "on" if form["is_pinned"] else ""
    return form


def _details_payload(note):
    result = build_note_details(note, current_user.id)
    return {
        "note": serialize_note(result.note),
        "latest_analysis": serialize_note_analysis(result.latest_analysis),
        "latest_failed_analysis": serialize_note_analysis(result.latest_failed_analysis),
        "task_suggestions": [serialize_note_suggestion(x) for x in result.task_suggestions],
        "question_history": [serialize_note_question(x) for x in result.question_history],
        "insights": result.insights,
        "project_context": result.project_context,
        "analysis_is_stale": bool(result.analysis_is_stale),
    }


@notes_api_bp.get("")
@api_auth_required
def list_notes_route():
    result = list_notes(
        current_user.id,
        request.args.get("q", ""),
        request.args.get("type", "all"),
        request.args.get("project", "all"),
    )
    return jsonify({
        "items": [serialize_note(x) for x in result.notes],
        "pinned": [serialize_note(x) for x in result.pinned_notes],
        "regular": [serialize_note(x) for x in result.regular_notes],
        "projects": [serialize_project_summary(x) for x in result.projects],
        "note_types": list(NOTE_TYPES),
        "filters": {
            "q": result.search_text,
            "type": result.selected_type,
            "project": result.selected_project,
        },
    })


@notes_api_bp.post("")
@api_auth_required
def create_note_route():
    try:
        data = build_note_input(_note_form(json_body()), current_user.id)
        note = create_note(current_user.id, data)
    except NoteValidationError as error:
        return validation_error(str(error))
    except NotePersistenceError:
        current_app.logger.exception("API note create failed")
        return persistence_error("LifeOS could not save the note.")
    return jsonify({"item": serialize_note(note)}), 201


@notes_api_bp.get("/<int:note_id>")
@api_auth_required
def note_details_route(note_id: int):
    try:
        note = require_owned_note(note_id, current_user.id)
    except NoteNotFoundError:
        return not_found("Note not found.")
    return jsonify(_details_payload(note))


@notes_api_bp.patch("/<int:note_id>")
@api_auth_required
def update_note_route(note_id: int):
    try:
        note = require_owned_note(note_id, current_user.id)
        data = build_note_input(_note_form(json_body(), note), current_user.id)
        note = update_note(note, data)
    except NoteNotFoundError:
        return not_found("Note not found.")
    except NoteValidationError as error:
        return validation_error(str(error))
    except NotePersistenceError:
        return persistence_error("LifeOS could not save the note.")
    return jsonify({"item": serialize_note(note)})


@notes_api_bp.delete("/<int:note_id>")
@api_auth_required
def delete_note_route(note_id: int):
    try:
        note = require_owned_note(note_id, current_user.id)
        title = delete_note(note)
    except NoteNotFoundError:
        return not_found("Note not found.")
    except NotePersistenceError:
        return persistence_error("LifeOS could not delete the note.")
    return jsonify({"deleted": True, "title": title})


@notes_api_bp.post("/<int:note_id>/pin")
@api_auth_required
def pin_note_route(note_id: int):
    try:
        note = require_owned_note(note_id, current_user.id)
        pinned = toggle_note_pin(note)
    except NoteNotFoundError:
        return not_found("Note not found.")
    except NotePersistenceError:
        return persistence_error("LifeOS could not update the note.")
    return jsonify({"pinned": pinned})


@notes_api_bp.post("/<int:note_id>/analyze")
@api_auth_required
def analyze_note_route(note_id: int):
    try:
        note = require_owned_note(note_id, current_user.id)
        project_context = build_project_context(note, current_user.id)
        result = analyze_note(
            title=note.title,
            content=note.content,
            note_type=note.note_type,
            project_context=project_context,
        )
        save_completed_analysis(note, current_user.id, result, project_context)
        return jsonify(_details_payload(note))
    except NoteNotFoundError:
        return not_found("Note not found.")
    except AIServiceError as error:
        try:
            save_failed_analysis(note, current_user.id, str(error))
        except Exception:
            pass
        return jsonify({"error": "ai_unavailable", "message": str(error)}), 503
    except NotePersistenceError:
        return persistence_error("LifeOS could not save the note analysis.")


@notes_api_bp.post("/<int:note_id>/ask")
@api_auth_required
def ask_note_route(note_id: int):
    payload = json_body()
    question = str(payload.get("question") or "").strip()
    if not question:
        return validation_error("Please enter a question.")
    if len(question) > 2000:
        return validation_error("The question cannot exceed 2,000 characters.")
    try:
        note = require_owned_note(note_id, current_user.id)
        project_context = build_project_context(note, current_user.id)
        latest_analysis = get_latest_completed_analysis(note, current_user.id)
        if latest_analysis is None:
            return validation_error("Analyze the note before asking follow-up questions.")
        if analysis_is_stale(note, latest_analysis, project_context):
            return validation_error("The note or linked project changed. Analyze it again first.")
        result = ask_about_note(
            title=note.title,
            content=note.content,
            question=question,
            analysis=latest_analysis.insights,
            project_context=project_context,
        )
        saved = save_completed_question(note, latest_analysis, current_user.id, question, result)
        return jsonify({"item": serialize_note_question(saved)})
    except NoteNotFoundError:
        return not_found("Note not found.")
    except AIServiceError as error:
        try:
            save_failed_question(note, latest_analysis, current_user.id, question, str(error))
        except Exception:
            pass
        return jsonify({"error": "ai_unavailable", "message": str(error)}), 503
    except NotePersistenceError:
        return persistence_error("LifeOS could not save the answer.")


@notes_api_bp.post("/<int:note_id>/suggestions/<int:suggestion_id>/approve")
@api_auth_required
def approve_note_suggestion_route(note_id: int, suggestion_id: int):
    try:
        note = require_owned_note(note_id, current_user.id)
        suggestion = require_owned_suggestion(note_id, suggestion_id, current_user.id)
        task = approve_suggestion(note, suggestion, current_user.id)
    except (NoteNotFoundError, NoteSuggestionNotFoundError):
        return not_found("Suggestion not found.")
    except NoteWorkflowError as error:
        return validation_error(str(error))
    except NotePersistenceError:
        return persistence_error("LifeOS could not create the task.")
    return jsonify({"task": serialize_task(task)})


@notes_api_bp.post("/<int:note_id>/suggestions/<int:suggestion_id>/reject")
@api_auth_required
def reject_note_suggestion_route(note_id: int, suggestion_id: int):
    try:
        require_owned_note(note_id, current_user.id)
        suggestion = require_owned_suggestion(note_id, suggestion_id, current_user.id)
        result = reject_suggestion(suggestion)
    except (NoteNotFoundError, NoteSuggestionNotFoundError):
        return not_found("Suggestion not found.")
    except NoteWorkflowError as error:
        return validation_error(str(error))
    except NotePersistenceError:
        return persistence_error("LifeOS could not update the suggestion.")
    return jsonify({"status": result})

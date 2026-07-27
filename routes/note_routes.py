"""HTTP routes for LifeOS Notes and AI Notes."""

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
    create_note as create_note_record,
    delete_note as delete_note_record,
    get_latest_completed_analysis,
    list_notes,
    list_owned_projects,
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


note_bp = Blueprint("note_bp", __name__, url_prefix="/notes")


@note_bp.before_request
@login_required
def protect_note_routes():
    return None


def _owned_note_or_404(note_id: int):
    try:
        return require_owned_note(note_id, current_user.id)
    except NoteNotFoundError:
        abort(404)


def _owned_suggestion_or_404(note_id: int, suggestion_id: int):
    try:
        return require_owned_suggestion(
            note_id,
            suggestion_id,
            current_user.id,
        )
    except NoteSuggestionNotFoundError:
        abort(404)


@note_bp.route("/", methods=["GET"])
def notes():
    result = list_notes(
        owner_id=current_user.id,
        search_text=request.args.get("q", ""),
        selected_type=request.args.get("type", "all"),
        selected_project=request.args.get("project", "all"),
    )
    return render_template(
        "notes.html",
        notes=result.notes,
        pinned_notes=result.pinned_notes,
        regular_notes=result.regular_notes,
        projects=result.projects,
        note_types=NOTE_TYPES,
        search_text=result.search_text,
        selected_type=result.selected_type,
        selected_project=result.selected_project,
    )


@note_bp.route("/create", methods=["POST"])
def create_note():
    try:
        data = build_note_input(request.form, current_user.id)
        note = create_note_record(current_user.id, data)
        flash(f'Note "{note.title}" created successfully.', "success")
        return redirect(url_for("note_bp.note_details", note_id=note.id))
    except NoteValidationError as error:
        flash(str(error), "error")
    except NotePersistenceError:
        current_app.logger.exception("LifeOS could not create a note.")
        flash("LifeOS could not save the note.", "error")
    return redirect(url_for("note_bp.notes"))


@note_bp.route("/<int:note_id>", methods=["GET"])
def note_details(note_id):
    note = _owned_note_or_404(note_id)
    result = build_note_details(note, current_user.id)
    return render_template(
        "note_details.html",
        note=result.note,
        latest_analysis=result.latest_analysis,
        latest_failed_analysis=result.latest_failed_analysis,
        task_suggestions=result.task_suggestions,
        question_history=result.question_history,
        insights=result.insights,
        project_context=result.project_context,
        project_task_lookup=result.project_task_lookup,
        analysis_is_stale=result.analysis_is_stale,
    )


@note_bp.route("/<int:note_id>/analyze", methods=["POST"])
def analyze_note_action(note_id):
    note = _owned_note_or_404(note_id)
    project_context = build_project_context(note, current_user.id)
    try:
        result = analyze_note(
            title=note.title,
            content=note.content,
            note_type=note.note_type,
            project_context=project_context,
        )
        save_completed_analysis(
            note,
            current_user.id,
            result,
            project_context,
        )
        if project_context:
            flash(
                "LifeOS analyzed the note with its linked project, tasks, and recent notes.",
                "success",
            )
        else:
            flash(
                "LifeOS turned the note into a clear insight and action plan.",
                "success",
            )
    except AIServiceError as error:
        try:
            save_failed_analysis(note, current_user.id, str(error))
        except NotePersistenceError:
            current_app.logger.exception(
                "LifeOS could not record the failed note analysis."
            )
        flash(str(error), "error")
    except NotePersistenceError:
        current_app.logger.exception(
            "LifeOS could not persist the note analysis for note %s.",
            note.id,
        )
        flash("LifeOS could not save the note analysis.", "error")
    except Exception:
        current_app.logger.exception(
            "Unexpected note-analysis failure for note %s.",
            note.id,
        )
        flash("LifeOS could not analyze the note.", "error")

    return redirect(
        url_for("note_bp.note_details", note_id=note.id) + "#lifeos-insight"
    )


@note_bp.route("/<int:note_id>/ask", methods=["POST"])
def ask_note_question(note_id):
    note = _owned_note_or_404(note_id)
    project_context = build_project_context(note, current_user.id)
    question = (request.form.get("question") or "").strip()

    if not question:
        flash("Please enter a question.", "error")
        return redirect(
            url_for("note_bp.note_details", note_id=note.id) + "#ask-lifeos"
        )
    if len(question) > 2_000:
        flash("The question cannot exceed 2,000 characters.", "error")
        return redirect(
            url_for("note_bp.note_details", note_id=note.id) + "#ask-lifeos"
        )

    latest_analysis = get_latest_completed_analysis(note, current_user.id)
    if latest_analysis is None:
        flash("Analyze the note before asking follow-up questions.", "error")
        return redirect(url_for("note_bp.note_details", note_id=note.id))
    if analysis_is_stale(note, latest_analysis, project_context):
        flash(
            "The note or linked project changed after the last analysis. Analyze it again first."
            if project_context
            else "This note changed after its last analysis. Analyze it again first.",
            "error",
        )
        return redirect(
            url_for("note_bp.note_details", note_id=note.id) + "#lifeos-insight"
        )

    try:
        result = ask_about_note(
            title=note.title,
            content=note.content,
            question=question,
            analysis=latest_analysis.insights,
            project_context=project_context,
        )
        save_completed_question(
            note,
            latest_analysis,
            current_user.id,
            question,
            result,
        )
        flash("LifeOS answered your question.", "success")
    except AIServiceError as error:
        try:
            save_failed_question(
                note,
                latest_analysis,
                current_user.id,
                question,
                str(error),
            )
        except NotePersistenceError:
            current_app.logger.exception(
                "LifeOS could not record the failed note question."
            )
        flash(str(error), "error")
    except NotePersistenceError:
        current_app.logger.exception(
            "LifeOS could not save a question for note %s.",
            note.id,
        )
        flash("LifeOS could not save the answer.", "error")
    except Exception:
        current_app.logger.exception(
            "Unexpected note-question failure for note %s.",
            note.id,
        )
        flash("LifeOS could not answer the question.", "error")

    return redirect(
        url_for("note_bp.note_details", note_id=note.id) + "#ask-lifeos"
    )


@note_bp.route(
    "/<int:note_id>/suggestions/<int:suggestion_id>/approve",
    methods=["POST"],
)
def approve_task_suggestion(note_id, suggestion_id):
    note = _owned_note_or_404(note_id)
    suggestion = _owned_suggestion_or_404(note.id, suggestion_id)
    try:
        already_approved = bool(
            suggestion.status == "Approved" and suggestion.created_task_id
        )
        task = approve_suggestion(note, suggestion, current_user.id)
        if already_approved:
            flash("This suggestion is already a LifeOS task.", "info")
        else:
            flash(f'Task "{task.title}" added to your workspace.', "success")
    except NoteWorkflowError as error:
        flash(str(error), "error")
    except NotePersistenceError:
        current_app.logger.exception(
            "LifeOS could not approve AI task suggestion %s.",
            suggestion.id,
        )
        flash("LifeOS could not create the task.", "error")
    return redirect(
        url_for("note_bp.note_details", note_id=note.id) + "#action-plan"
    )


@note_bp.route(
    "/<int:note_id>/suggestions/<int:suggestion_id>/reject",
    methods=["POST"],
)
def reject_task_suggestion(note_id, suggestion_id):
    note = _owned_note_or_404(note_id)
    suggestion = _owned_suggestion_or_404(note.id, suggestion_id)
    try:
        result = reject_suggestion(suggestion)
        flash(
            "This suggestion is already rejected."
            if result == "already_rejected"
            else "Suggestion rejected.",
            "info" if result == "already_rejected" else "success",
        )
    except NoteWorkflowError as error:
        flash(str(error), "error")
    except NotePersistenceError:
        current_app.logger.exception(
            "LifeOS could not reject AI task suggestion %s.",
            suggestion.id,
        )
        flash("LifeOS could not reject the suggestion.", "error")
    return redirect(
        url_for("note_bp.note_details", note_id=note.id) + "#action-plan"
    )


@note_bp.route("/<int:note_id>/edit", methods=["GET", "POST"])
def edit_note(note_id):
    note = _owned_note_or_404(note_id)
    if request.method == "POST":
        try:
            data = build_note_input(request.form, current_user.id)
            update_note(note, data)
            flash(
                "Note updated. Analyze it again to refresh the LifeOS insight.",
                "success",
            )
            return redirect(url_for("note_bp.note_details", note_id=note.id))
        except NoteValidationError as error:
            flash(str(error), "error")
        except NotePersistenceError:
            current_app.logger.exception(
                "LifeOS could not update note %s.",
                note.id,
            )
            flash("LifeOS could not update the note.", "error")
        return redirect(url_for("note_bp.edit_note", note_id=note.id))

    return render_template(
        "note_edit.html",
        note=note,
        projects=list_owned_projects(current_user.id),
        note_types=NOTE_TYPES,
    )


@note_bp.route("/<int:note_id>/pin", methods=["POST"])
def toggle_pin(note_id):
    note = _owned_note_or_404(note_id)
    try:
        is_pinned = toggle_note_pin(note)
        flash(
            "Note pinned successfully."
            if is_pinned
            else "Note unpinned successfully.",
            "success",
        )
    except NotePersistenceError:
        current_app.logger.exception(
            "LifeOS could not toggle note %s pin state.",
            note.id,
        )
        flash("LifeOS could not update the note.", "error")
    return redirect(url_for("note_bp.note_details", note_id=note.id))


@note_bp.route("/<int:note_id>/delete", methods=["POST"])
def delete_note(note_id):
    note = _owned_note_or_404(note_id)
    try:
        title = delete_note_record(note)
        flash(f'Note "{title}" deleted successfully.', "success")
    except NotePersistenceError:
        current_app.logger.exception(
            "LifeOS could not delete note %s.",
            note.id,
        )
        flash("LifeOS could not delete the note.", "error")
    return redirect(url_for("note_bp.notes"))

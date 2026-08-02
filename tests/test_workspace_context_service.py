"""Tests for the shared LifeOS workspace context service."""

import pytest

from database import db
from models import Document, Note, Project, Task, User
from services.workspace_context_service import (
    WorkspaceContextNotFoundError,
    build_project_context,
)


def create_second_user() -> User:
    """Create another user for ownership and privacy tests."""

    second_user = User(
        name="Second User",
        email="second@example.com",
    )
    second_user.set_password("StrongPass123!")

    db.session.add(second_user)
    db.session.commit()

    return second_user


def test_project_context_contains_only_owned_information(app, user):
    with app.app_context():
        second_user = create_second_user()

        project = Project(
            user_id=user,
            title="LifeOS",
            description="Connected personal workspace",
            goal="Connect projects, tasks, notes and documents",
            status="In Progress",
            priority="High",
            progress=60,
        )

        db.session.add(project)
        db.session.commit()

        pending_task = Task(
            user_id=user,
            project_id=project.id,
            title="Build workspace context",
            status="Pending",
            importance="High",
        )

        completed_task = Task(
            user_id=user,
            project_id=project.id,
            title="Refactor architecture",
            status="Completed",
            importance="Medium",
        )

        general_task = Task(
            user_id=user,
            project_id=None,
            title="General workspace task",
            status="Pending",
        )

        foreign_task = Task(
            user_id=second_user.id,
            project_id=project.id,
            title="Another user's task",
            status="Pending",
        )

        current_note = Note(
            user_id=user,
            project_id=project.id,
            title="Current note",
            content="This note is currently being analysed.",
            note_type="Project Note",
        )

        related_note = Note(
            user_id=user,
            project_id=project.id,
            title="Related note",
            content="This is useful related project information.",
            note_type="Project Note",
        )

        general_note = Note(
            user_id=user,
            project_id=None,
            title="General note",
            content="This note is not connected to the project.",
            note_type="Quick Note",
        )

        foreign_note = Note(
            user_id=second_user.id,
            project_id=project.id,
            title="Another user's note",
            content="This note must never appear in the context.",
            note_type="Project Note",
        )

        project_document = Document(
            project_id=project.id,
            filename="lifeos_requirements.pdf",
            file_path="instance/storage/lifeos_requirements.pdf",
            extracted_text=(
                "LifeOS should connect projects, tasks, notes, "
                "documents and intelligent planning."
            ),
            summary=(
                "Requirements for the connected LifeOS workspace."
            ),
            detected_modules=(
                "Projects, Tasks, Notes, Documents"
            ),
            extracted_tasks=(
                "Build PDF upload and document analysis."
            ),
        )

        general_document = Document(
            project_id=None,
            filename="general_document.pdf",
            file_path="instance/storage/general_document.pdf",
            extracted_text=(
                "This document is not linked to the LifeOS project."
            ),
        )

        db.session.add_all(
            [
                pending_task,
                completed_task,
                general_task,
                foreign_task,
                current_note,
                related_note,
                general_note,
                foreign_note,
                project_document,
                general_document,
            ]
        )
        db.session.commit()

        context = build_project_context(
            owner_id=user,
            project_id=project.id,
            exclude_note_id=current_note.id,
        )

        assert context["project"]["title"] == "LifeOS"
        assert context["project"]["progress"] == 60

        task_titles = [
            task["title"]
            for task in context["tasks"]
        ]

        assert task_titles == [
            "Build workspace context",
            "Refactor architecture",
        ]

        assert "General workspace task" not in task_titles
        assert "Another user's task" not in task_titles

        assert context["task_status_summary"] == {
            "Pending": 1,
            "Completed": 1,
        }

        note_titles = [
            note["title"]
            for note in context["recent_related_notes"]
        ]

        assert note_titles == ["Related note"]

        assert "Current note" not in note_titles
        assert "General note" not in note_titles
        assert "Another user's note" not in note_titles

        documents = context["documents"]

        assert len(documents) == 1

        assert (
            documents[0]["filename"]
            == "lifeos_requirements.pdf"
        )

        assert documents[0]["summary"] == (
            "Requirements for the connected LifeOS workspace."
        )

        assert documents[0]["has_extracted_text"] is True

        assert (
            "Build PDF upload"
            in documents[0]["extracted_tasks"]
        )

        document_filenames = [
            document["filename"]
            for document in documents
        ]

        assert "general_document.pdf" not in document_filenames

        assert (
            context["context_counts"]["total_project_tasks"]
            == 2
        )
        assert (
            context["context_counts"]["tasks_considered"]
            == 2
        )
        assert (
            context["context_counts"][
                "related_notes_considered"
            ]
            == 1
        )
        assert (
            context["context_counts"][
                "documents_considered"
            ]
            == 1
        )


def test_project_context_blocks_another_users_project(app, user):
    with app.app_context():
        second_user = create_second_user()

        private_project = Project(
            user_id=second_user.id,
            title="Private Project",
            status="In Progress",
            priority="Medium",
        )

        db.session.add(private_project)
        db.session.commit()

        with pytest.raises(WorkspaceContextNotFoundError):
            build_project_context(
                owner_id=user,
                project_id=private_project.id,
            )
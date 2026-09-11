from __future__ import annotations

from types import SimpleNamespace

import pytest

from database import db
from models import (
    Document,
    DocumentCollection,
    DocumentCollectionItem,
    LearningModule,
    ModuleDocumentLink,
    Note,
    Task,
)
from services.module_question_workflow_service import (
    NO_MATCH_ANSWER,
    ask_owned_module_documents,
    create_module_source_fingerprint,
)
from services.module_service import (
    ModuleNotFoundError,
    create_lecture,
    create_module,
    delete_module,
    link_collection,
    link_document,
    link_note,
    link_task,
    require_owned_module,
)


def _document(user_id: int, filename: str, text: str) -> Document:
    row = Document(
        user_id=user_id,
        project_id=None,
        filename=filename,
        file_path=f"user-{user_id}-documents/{filename}",
        extracted_text=text,
        is_current_version=True,
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_module_and_lecture_are_first_class_owned_objects(app, user):
    with app.app_context():
        module = create_module(
            user_id=user,
            title="Linear Algebra",
            subject="Mathematics",
            description="Matrices and vector spaces",
        )
        lecture = create_lecture(
            module_id=module.id,
            user_id=user,
            title="Geometry of Linear Equations",
            lecture_number=1,
            status="Planned",
            topics="systems, geometry",
        )

        loaded = require_owned_module(module.id, user)
        assert loaded.title == "Linear Algebra"
        assert len(loaded.lectures) == 1
        assert lecture.module_id == module.id
        assert lecture.lecture_number == 1


def test_module_resources_are_links_not_clones_and_survive_module_delete(app, user):
    with app.app_context():
        module = create_module(user_id=user, title="Machine Learning")
        lecture = create_lecture(
            module_id=module.id,
            user_id=user,
            title="Regression",
            lecture_number=1,
        )
        document = _document(user, "regression.pdf", "Linear regression minimizes squared error.")
        note = Note(user_id=user, title="Loss", content="MSE intuition", note_type="Quick Note")
        task = Task(user_id=user, title="Solve regression sheet")
        collection = DocumentCollection(user_id=user, name="Midterm", description=None)
        db.session.add_all([note, task, collection])
        db.session.commit()

        link_document(module_id=module.id, document_id=document.id, user_id=user, lecture_id=lecture.id)
        link_note(module_id=module.id, note_id=note.id, user_id=user, lecture_id=lecture.id)
        link_task(module_id=module.id, task_id=task.id, user_id=user, lecture_id=lecture.id)
        link_collection(module_id=module.id, collection_id=collection.id, user_id=user)

        db.session.expire_all()
        loaded = require_owned_module(module.id, user)
        assert len(loaded.document_links) == 1
        assert len(loaded.note_links) == 1
        assert len(loaded.task_links) == 1
        assert len(loaded.collection_links) == 1

        delete_module(module_id=module.id, user_id=user)

        assert Document.query.get(document.id) is not None
        assert Note.query.get(note.id) is not None
        assert Task.query.get(task.id) is not None
        assert DocumentCollection.query.get(collection.id) is not None
        assert ModuleDocumentLink.query.filter_by(module_id=module.id).count() == 0


def test_module_ownership_blocks_cross_user_access(app, user):
    from models import User

    with app.app_context():
        other = User(name="Other", email="other-modules@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()
        module = create_module(user_id=user, title="Private module")

        with pytest.raises(ModuleNotFoundError):
            require_owned_module(module.id, other.id)


def test_module_source_fingerprint_changes_when_document_content_changes(app, user):
    with app.app_context():
        module = create_module(user_id=user, title="Databases")
        document = _document(user, "db.pdf", "Normalization reduces update anomalies.")
        link_document(module_id=module.id, document_id=document.id, user_id=user)

        before = create_module_source_fingerprint(module_id=module.id, user_id=user)
        document.extracted_text = "Normalization reduces update anomalies. BCNF is stricter than 3NF."
        db.session.commit()
        after = create_module_source_fingerprint(module_id=module.id, user_id=user)

        assert before != after


def test_ask_module_scopes_retrieval_to_all_linked_documents_and_stays_grounded(app, user, monkeypatch):
    import services.module_question_workflow_service as workflow

    with app.app_context():
        module = create_module(user_id=user, title="Northstar Training")
        first = _document(user, "operations.pdf", "Project codename AURORA-26.")
        second = _document(user, "finance.pdf", "Approved budget EGP 8.4 million.")
        link_document(module_id=module.id, document_id=first.id, user_id=user)
        link_document(module_id=module.id, document_id=second.id, user_id=user)

        captured = {}

        def fake_retrieve(*, documents, user_id, query, **kwargs):
            captured["document_ids"] = sorted(item.id for item in documents)
            return SimpleNamespace(query=query, chunks=[], document_count=len(documents))

        monkeypatch.setattr(workflow, "retrieve_owned_document_set", fake_retrieve)
        monkeypatch.setattr(workflow, "build_scope_context", lambda result: "verified context")
        monkeypatch.setattr(
            workflow,
            "verify_document_answerability",
            lambda **kwargs: SimpleNamespace(answerable=False, provider="test", model="test", source_ids=[]),
        )

        result = ask_owned_module_documents(
            module_id=module.id,
            user_id=user,
            question_text="What is the CEO salary?",
        )

        assert captured["document_ids"] == sorted([first.id, second.id])
        assert result.question.answer == NO_MATCH_ANSWER
        assert result.question.sources == []


def test_ask_lecture_only_scopes_documents_linked_to_that_lecture(app, user, monkeypatch):
    import services.module_question_workflow_service as workflow

    with app.app_context():
        module = create_module(user_id=user, title="Algorithms")
        lecture_one = create_lecture(module_id=module.id, user_id=user, title="Sorting", lecture_number=1)
        lecture_two = create_lecture(module_id=module.id, user_id=user, title="Graphs", lecture_number=2)
        sorting = _document(user, "sorting.pdf", "Merge sort is O(n log n).")
        graphs = _document(user, "graphs.pdf", "BFS explores by levels.")
        link_document(module_id=module.id, document_id=sorting.id, user_id=user, lecture_id=lecture_one.id)
        link_document(module_id=module.id, document_id=graphs.id, user_id=user, lecture_id=lecture_two.id)

        captured = {}

        def fake_retrieve(*, documents, user_id, query, **kwargs):
            captured["ids"] = [item.id for item in documents]
            return SimpleNamespace(query=query, chunks=[], document_count=len(documents))

        monkeypatch.setattr(workflow, "retrieve_owned_document_set", fake_retrieve)
        monkeypatch.setattr(workflow, "build_scope_context", lambda result: "verified context")
        monkeypatch.setattr(
            workflow,
            "verify_document_answerability",
            lambda **kwargs: SimpleNamespace(answerable=False, provider="test", model="test", source_ids=[]),
        )

        ask_owned_module_documents(
            module_id=module.id,
            lecture_id=lecture_one.id,
            user_id=user,
            question_text="What is the complexity?",
        )

        assert captured["ids"] == [sorting.id]



def test_ask_module_includes_documents_from_linked_collections(app, user, monkeypatch):
    import services.module_question_workflow_service as workflow

    with app.app_context():
        module = create_module(user_id=user, title="Exam Revision")
        direct = _document(user, "lecture.pdf", "Direct module evidence.")
        collected = _document(user, "past-exam.pdf", "Collection-only evidence.")
        link_document(module_id=module.id, document_id=direct.id, user_id=user)

        collection = DocumentCollection(user_id=user, name="Final Revision", description=None)
        db.session.add(collection)
        db.session.flush()
        db.session.add(DocumentCollectionItem(collection_id=collection.id, document_id=collected.id))
        db.session.commit()
        link_collection(module_id=module.id, collection_id=collection.id, user_id=user)

        captured = {}

        def fake_retrieve(*, documents, user_id, query, **kwargs):
            captured["ids"] = sorted(item.id for item in documents)
            return SimpleNamespace(query=query, chunks=[], document_count=len(documents))

        monkeypatch.setattr(workflow, "retrieve_owned_document_set", fake_retrieve)
        monkeypatch.setattr(workflow, "build_scope_context", lambda result: "verified context")
        monkeypatch.setattr(
            workflow,
            "verify_document_answerability",
            lambda **kwargs: SimpleNamespace(answerable=False, provider="test", model="test", source_ids=[]),
        )

        ask_owned_module_documents(
            module_id=module.id,
            user_id=user,
            question_text="What should I revise?",
        )

        assert captured["ids"] == sorted([direct.id, collected.id])


def test_ask_lecture_does_not_implicitly_expand_linked_collections(app, user, monkeypatch):
    import services.module_question_workflow_service as workflow

    with app.app_context():
        module = create_module(user_id=user, title="Operating Systems")
        lecture = create_lecture(module_id=module.id, user_id=user, title="Scheduling", lecture_number=1)
        lecture_doc = _document(user, "scheduling.pdf", "Round robin uses a time quantum.")
        collection_doc = _document(user, "revision.pdf", "A broad module revision document.")
        link_document(module_id=module.id, document_id=lecture_doc.id, user_id=user, lecture_id=lecture.id)

        collection = DocumentCollection(user_id=user, name="All Revision", description=None)
        db.session.add(collection)
        db.session.flush()
        db.session.add(DocumentCollectionItem(collection_id=collection.id, document_id=collection_doc.id))
        db.session.commit()
        link_collection(module_id=module.id, collection_id=collection.id, user_id=user)

        captured = {}

        def fake_retrieve(*, documents, user_id, query, **kwargs):
            captured["ids"] = [item.id for item in documents]
            return SimpleNamespace(query=query, chunks=[], document_count=len(documents))

        monkeypatch.setattr(workflow, "retrieve_owned_document_set", fake_retrieve)
        monkeypatch.setattr(workflow, "build_scope_context", lambda result: "verified context")
        monkeypatch.setattr(
            workflow,
            "verify_document_answerability",
            lambda **kwargs: SimpleNamespace(answerable=False, provider="test", model="test", source_ids=[]),
        )

        ask_owned_module_documents(
            module_id=module.id,
            lecture_id=lecture.id,
            user_id=user,
            question_text="What scheduling policy is described?",
        )

        assert captured["ids"] == [lecture_doc.id]

def test_projectless_document_is_owned_directly_by_user(app, user):
    from services.document_access_service import require_owned_document

    with app.app_context():
        document = _document(user, "lecture.pdf", "A lecture document can exist without a Project.")
        loaded = require_owned_document(document.id, user)
        assert loaded.user_id == user
        assert loaded.project_id is None

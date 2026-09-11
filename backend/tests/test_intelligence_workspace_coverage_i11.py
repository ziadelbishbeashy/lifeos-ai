from __future__ import annotations

from datetime import date, timedelta

from database import db
from models import Document, LearningModule, Lecture, Project, Task, User
from services.intelligence_ask_service import ask_lifeos
from services.intelligence_intent_router_service import route_intelligence_request


def _project(user_id: int, title: str, **kwargs) -> Project:
    project = Project(
        user_id=user_id,
        title=title,
        status=kwargs.pop("status", "In Progress"),
        priority=kwargs.pop("priority", "Medium"),
        progress=kwargs.pop("progress", 25),
        **kwargs,
    )
    db.session.add(project)
    db.session.commit()
    return project


def _task(user_id: int, title: str, *, project_id: int | None = None, deadline=None, status="Pending") -> Task:
    task = Task(
        user_id=user_id,
        project_id=project_id,
        title=title,
        deadline=deadline,
        status=status,
        importance="High",
        difficulty="Medium",
    )
    db.session.add(task)
    db.session.commit()
    return task


def test_i11_router_recognizes_operational_intents(app, user):
    with app.app_context():
        _project(user, "LifeOS")
        cases = {
            "What should I do today?": "today_focus",
            "Which tasks are overdue?": "task_status",
            "What deadlines are coming up?": "deadline_review",
            "Which documents need review?": "document_review",
            "What am I missing?": "workspace_gaps",
            "What should I study next?": "study_next",
            "What is my LifeOS project progress?": "project_question",
        }
        for query, expected in cases.items():
            assert route_intelligence_request(query=query, owner_id=user).intent == expected



def test_i11_explicit_all_projects_does_not_trigger_scope_clarification(app, user):
    with app.app_context():
        _project(user, "LifeOS")
        _project(user, "Store")
        decision = route_intelligence_request(
            query="Which tasks are overdue across all my projects?",
            owner_id=user,
        )
        assert decision.intent == "task_status"
        assert decision.requires_clarification is False
        assert decision.scope_type == "portfolio"

        blocked = route_intelligence_request(
            query="Show blocked tasks across all projects",
            owner_id=user,
        )
        assert blocked.intent == "task_status"
        assert blocked.requires_clarification is False
        assert blocked.scope_type == "portfolio"


def test_i11_overdue_and_deadline_answers_are_verified_and_owned(app, user):
    with app.app_context():
        project = _project(user, "LifeOS", deadline=date.today() + timedelta(days=4))
        overdue = _task(user, "Fix deployment", project_id=project.id, deadline=date.today() - timedelta(days=2))
        due = _task(user, "Run regression", project_id=project.id, deadline=date.today() + timedelta(days=2))
        _task(user, "Already done", project_id=project.id, deadline=date.today() - timedelta(days=3), status="Completed")

        other = User(name="Other", email="i11-other@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()
        hidden_project = _project(other.id, "Hidden")
        _task(other.id, "Private overdue", project_id=hidden_project.id, deadline=date.today() - timedelta(days=9))

        overdue_result = ask_lifeos(query="Which tasks are overdue?", owner_id=user).to_dict()
        assert overdue_result["status"] == "completed"
        assert overdue_result["response_mode"] == "deterministic_verified"
        assert overdue_result["insight"]["kind"] == "overdue_tasks"
        titles = {item["title"] for item in overdue_result["insight"]["items"]}
        assert overdue.title in titles
        assert "Private overdue" not in titles
        assert "Already done" not in titles

        deadline_result = ask_lifeos(query="What deadlines are coming up this week?", owner_id=user).to_dict()
        deadline_titles = {item["title"] for item in deadline_result["insight"]["items"]}
        assert due.title in deadline_titles
        assert "LifeOS project deadline" in deadline_titles
        assert deadline_result["insight"]["verified_from_state"] is True


def test_i11_project_scoped_task_question_uses_clarification_context(app, user):
    with app.app_context():
        lifeos = _project(user, "LifeOS")
        store = _project(user, "Store")
        _task(user, "LifeOS overdue", project_id=lifeos.id, deadline=date.today() - timedelta(days=1))
        _task(user, "Store overdue", project_id=store.id, deadline=date.today() - timedelta(days=1))

        first = ask_lifeos(query="Which tasks are overdue in my project?", owner_id=user)
        assert first.status == "clarification_required"
        assert first.route.intent == "task_status"

        second = ask_lifeos(
            query="LifeOS",
            owner_id=user,
            clarification_context={"intent": "task_status"},
        ).to_dict()
        assert second["route"]["scope"]["label"] == "LifeOS"
        titles = {item["title"] for item in second["insight"]["items"]}
        assert "LifeOS overdue" in titles
        assert "Store overdue" not in titles


def test_i11_documents_needing_review_include_unanalysed_current_docs(app, user):
    with app.app_context():
        project = _project(user, "LifeOS")
        document = Document(
            user_id=user,
            project_id=project.id,
            filename="Architecture.pdf",
            file_path="test/architecture.pdf",
            extracted_text="Architecture notes",
            is_current_version=True,
        )
        db.session.add(document)
        db.session.commit()

        result = ask_lifeos(query="Which documents need review?", owner_id=user).to_dict()
        assert result["route"]["intent"] == "document_review"
        assert result["insight"]["kind"] == "documents_needing_review"
        item = next(item for item in result["insight"]["items"] if item["title"] == "Architecture.pdf")
        assert item["status"] == "Not analysed"
        assert item["project_title"] == "LifeOS"


def test_i11_study_next_prefers_in_progress_or_urgent_lecture(app, user):
    with app.app_context():
        module = LearningModule(user_id=user, title="Operating Systems", subject="OS", status="Active")
        db.session.add(module)
        db.session.flush()
        completed = Lecture(module_id=module.id, title="Processes", lecture_number=1, status="Completed")
        current = Lecture(module_id=module.id, title="Threads", lecture_number=2, status="In Progress")
        planned = Lecture(module_id=module.id, title="Scheduling", lecture_number=3, status="Planned")
        db.session.add_all([completed, current, planned])
        db.session.commit()

        result = ask_lifeos(query="What should I study next?", owner_id=user).to_dict()
        assert result["route"]["intent"] == "study_next"
        assert result["insight"]["kind"] == "study_next"
        assert result["insight"]["items"][0]["title"] == "Lecture 2: Threads"
        assert result["insight"]["items"][0]["module_title"] == "Operating Systems"


def test_i11_project_fact_and_today_focus_are_deterministic(app, user):
    with app.app_context():
        project = _project(user, "LifeOS", progress=63, current_phase="Development")
        _task(user, "Blocked integration", project_id=project.id, status="Blocked")

        fact = ask_lifeos(query="What is my LifeOS project progress?", owner_id=user).to_dict()
        assert fact["insight"]["kind"] == "project_fact"
        assert "63%" in fact["answer"]
        assert fact["verification"]["status"] == "verified"

        today = ask_lifeos(query="What should I do today?", owner_id=user).to_dict()
        assert today["insight"]["kind"] == "today_focus"
        assert today["insight"]["items"]
        assert "Blocked integration" in today["insight"]["items"][0]["title"]
        assert today["read_only"] is True

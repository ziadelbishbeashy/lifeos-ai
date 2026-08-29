from __future__ import annotations

from database import db
from models import Project, Task
from services.intelligence_ask_service import ask_lifeos
from services.intelligence_intent_router_service import route_intelligence_request
from services.project_review_agent_service import (
    build_portfolio_agent_answer,
    build_project_agent_answer,
    run_owned_portfolio_review_agent,
    run_owned_project_review_agent,
)


def _project(user_id: int, title: str, *, status: str = "In Progress") -> Project:
    project = Project(
        user_id=user_id,
        title=title,
        status=status,
        priority="Medium",
        progress=10,
    )
    db.session.add(project)
    db.session.commit()
    return project


def test_i8_router_separates_focus_request_from_status_review(app, user):
    with app.app_context():
        project = _project(user, "LifeOS")

        focus = route_intelligence_request(
            query="What should I focus on in LifeOS?",
            owner_id=user,
        )
        status = route_intelligence_request(
            query="How is my LifeOS project going?",
            owner_id=user,
        )

        assert focus.intent == "project_focus"
        assert focus.scope_id == project.id
        assert focus.status == "ready"
        assert status.intent == "project_review"


def test_i8_project_agent_prioritizes_blocked_task_and_remains_read_only(app, user):
    with app.app_context():
        project = _project(user, "LifeOS")
        blocked = Task(
            user_id=user,
            project_id=project.id,
            title="Fix deployment blocker",
            status="Blocked",
            importance="High",
        )
        later = Task(
            user_id=user,
            project_id=project.id,
            title="Polish dashboard",
            status="Pending",
            importance="Medium",
        )
        db.session.add_all([blocked, later])
        db.session.commit()

        before = [(item.id, item.status) for item in Task.query.filter_by(project_id=project.id).order_by(Task.id).all()]
        result = run_owned_project_review_agent(project_id=project.id, owner_id=user)
        after = [(item.id, item.status) for item in Task.query.filter_by(project_id=project.id).order_by(Task.id).all()]

        assert result.priorities
        assert result.priorities[0].category == "blocked_task"
        assert result.priorities[0].title == "Unblock: Fix deployment blocker"
        assert result.attention_level == "high"
        assert before == after
        public = result.to_dict()
        assert public["read_only"] is True
        assert "score" not in public["priorities"][0]
        assert "reviewed_steps" not in public


def test_i8_active_project_without_tasks_gets_safe_next_action_suggestion(app, user):
    with app.app_context():
        project = _project(user, "Empty Active Project")
        result = run_owned_project_review_agent(project_id=project.id, owner_id=user)

        assert result.priorities
        assert result.priorities[0].category == "missing_next_action"
        assert "next concrete project task" in result.priorities[0].title.lower()


def test_i8_portfolio_agent_ranks_blocked_project_before_low_urgency_projects(app, user):
    with app.app_context():
        blocked_project = _project(user, "Blocked Project")
        idle_project = _project(user, "Idle Project")
        db.session.add(
            Task(
                user_id=user,
                project_id=blocked_project.id,
                title="Waiting on API access",
                status="Blocked",
                importance="High",
            )
        )
        db.session.commit()

        result = run_owned_portfolio_review_agent(owner_id=user)

        assert result.reviewed_projects == 2
        assert result.priorities
        assert result.priorities[0].project_id == blocked_project.id
        assert result.priorities[0].category == "blocked_task"
        assert any(item.project_id == idle_project.id for item in result.priorities)


def test_i8_ask_lifeos_returns_verified_agent_payload_for_focus(app, user):
    with app.app_context():
        project = _project(user, "LifeOS")
        db.session.add(
            Task(
                user_id=user,
                project_id=project.id,
                title="Finish intelligence tests",
                status="Blocked",
                importance="Critical",
            )
        )
        db.session.commit()

        result = ask_lifeos(
            query="What should I focus on in LifeOS?",
            owner_id=user,
        )
        payload = result.to_dict()

        assert payload["status"] == "completed"
        assert payload["response_mode"] == "agent_verified"
        assert payload["verification"]["status"] == "verified"
        assert payload["agent"]["kind"] == "project_review_agent"
        assert payload["agent"]["priorities"][0]["category"] == "blocked_task"
        assert "Finish intelligence tests" in payload["answer"]
        assert payload["read_only"] is True


def test_i8_focus_clarification_all_continues_as_portfolio_agent(app, user):
    with app.app_context():
        _project(user, "LifeOS")
        _project(user, "Storefront")

        first = ask_lifeos(query="What should I focus on in my project?", owner_id=user)
        assert first.status == "clarification_required"
        assert first.route.intent == "project_focus"

        second = ask_lifeos(
            query="all",
            owner_id=user,
            clarification_context={"intent": "project_focus"},
        )
        payload = second.to_dict()
        assert payload["status"] == "completed"
        assert payload["route"]["intent"] == "portfolio_focus"
        assert payload["response_mode"] == "agent_verified"
        assert payload["agent"]["kind"] == "portfolio_review_agent"


def test_i8_attention_wording_preserves_focus_intent_through_all_clarification(app, user):
    """Regression for the Ask LifeOS UI wording used by the product suggestion.

    "Review my project and tell me what needs attention" is a prioritization
    request, not a passive status summary.  If the user then chooses "all",
    the continuation must remain the portfolio focus agent.
    """

    with app.app_context():
        _project(user, "LifeOS")
        _project(user, "test")

        first = ask_lifeos(
            query="Review my project and tell me what needs attention",
            owner_id=user,
        )
        assert first.status == "clarification_required"
        assert first.route.intent == "project_focus"

        second = ask_lifeos(
            query="all",
            owner_id=user,
            clarification_context={"intent": first.route.intent},
        )
        payload = second.to_dict()

        assert payload["status"] == "completed"
        assert payload["route"]["intent"] == "portfolio_focus"
        assert payload["response_mode"] == "agent_verified"
        assert payload["agent"]["kind"] == "portfolio_review_agent"
        assert payload["agent"]["priorities"]


def test_i8_explicit_project_attention_wording_routes_directly_to_agent(app, user):
    with app.app_context():
        project = _project(user, "LifeOS")

        route = route_intelligence_request(
            query="Review LifeOS and tell me what needs attention",
            owner_id=user,
        )

        assert route.intent == "project_focus"
        assert route.scope_id == project.id
        assert route.status == "ready"


def test_i8_agent_answer_is_concise_and_does_not_duplicate_priority_details(app, user):
    with app.app_context():
        project = _project(user, "LifeOS")
        db.session.add_all([
            Task(user_id=user, project_id=project.id, title="Blocker one", status="Blocked", importance="High"),
            Task(user_id=user, project_id=project.id, title="Blocker two", status="Blocked", importance="High"),
        ])
        db.session.commit()

        project_agent = run_owned_project_review_agent(project_id=project.id, owner_id=user)
        project_answer = build_project_agent_answer(project_agent)
        assert "Top focus:" in project_answer
        assert "Next:" not in project_answer
        assert project_answer.count("Blocker") <= 1

        portfolio_agent = run_owned_portfolio_review_agent(owner_id=user)
        portfolio_answer = build_portfolio_agent_answer(portfolio_agent)
        assert "Top focus:" in portfolio_answer
        assert "Next:" not in portfolio_answer
        assert "ranked priorit" in portfolio_answer

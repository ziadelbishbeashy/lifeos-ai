from datetime import date, timedelta

from database import db
from models import Project, SmartPlannerPlan, Task


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "StrongPass123!"},
    )
    assert response.status_code == 200


def _workspace(user):
    project = Project(
        user_id=user,
        title="V-SPACE V1",
        status="In Progress",
        priority="High",
        deadline=date.today() + timedelta(days=3),
    )
    db.session.add(project)
    db.session.flush()
    urgent = Task(
        user_id=user,
        project_id=project.id,
        title="Fix deployment blocker",
        importance="Critical",
        difficulty="Medium",
        deadline=date.today(),
        status="Pending",
        priority_score=90,
    )
    later = Task(
        user_id=user,
        project_id=project.id,
        title="Polish empty states",
        importance="Low",
        difficulty="Easy",
        deadline=date.today() + timedelta(days=6),
        status="Pending",
        priority_score=10,
    )
    db.session.add_all([urgent, later])
    db.session.commit()
    return project.id, urgent.id, later.id


def test_smart_planner_preview_is_read_only_and_prioritizes_urgent_work(app, client, user):
    with app.app_context():
        project_id, urgent_id, _ = _workspace(user)

    _login(client)
    response = client.post(
        "/api/v1/planner/preview",
        json={
            "mode": "day",
            "start_date": date.today().isoformat(),
            "working_start": "09:00",
            "working_end": "17:00",
            "break_minutes": 15,
            "project_id": project_id,
        },
    )
    assert response.status_code == 200
    preview = response.get_json()["preview"]
    assert preview["read_only"] is True
    assert preview["verified_from_state"] is True
    assert preview["confirmation_required"] is True
    assert preview["days"][0]["blocks"][0]["task_id"] == urgent_id
    assert preview["scheduled_tasks"] == 2

    with app.app_context():
        assert SmartPlannerPlan.query.count() == 0


def test_smart_planner_requires_i9_confirmation_before_plan_is_saved(app, client, user):
    with app.app_context():
        project_id, _, _ = _workspace(user)

    _login(client)
    prepared = client.post(
        "/api/v1/planner/proposals",
        json={
            "mode": "day",
            "start_date": date.today().isoformat(),
            "working_start": "09:00",
            "working_end": "17:00",
            "break_minutes": 15,
            "project_id": project_id,
            "request_text": "Help me finish the most important V-SPACE work today",
        },
    )
    assert prepared.status_code == 201
    proposal = prepared.get_json()["proposal"]
    assert proposal["action_type"] == "apply_smart_plan"
    assert proposal["status"] == "pending"
    assert proposal["requires_confirmation"] is True

    with app.app_context():
        assert SmartPlannerPlan.query.count() == 0

    confirmed = client.post(f"/api/v1/intelligence/action-proposals/{proposal['id']}/confirm")
    assert confirmed.status_code == 200
    result = confirmed.get_json()["proposal"]
    assert result["status"] == "confirmed"
    assert result["execution"]["resource_type"] == "smart_plan"

    with app.app_context():
        plan = SmartPlannerPlan.query.filter_by(user_id=user, status="accepted").one()
        assert plan.mode == "day"
        assert len(plan.blocks) == 2
        assert plan.request_text == "Help me finish the most important V-SPACE work today"


def test_smart_planner_reports_overload_instead_of_overfilling(app, client, user):
    with app.app_context():
        project_id, _, _ = _workspace(user)
        for index in range(4):
            db.session.add(Task(
                user_id=user,
                project_id=project_id,
                title=f"Hard work {index}",
                importance="High",
                difficulty="Hard",
                status="Pending",
                priority_score=50,
            ))
        db.session.commit()

    _login(client)
    response = client.post(
        "/api/v1/planner/preview",
        json={
            "mode": "day",
            "start_date": date.today().isoformat(),
            "working_start": "09:00",
            "working_end": "11:00",
            "break_minutes": 15,
            "project_id": project_id,
        },
    )
    assert response.status_code == 200
    preview = response.get_json()["preview"]
    assert preview["overload_minutes"] > 0
    assert preview["unscheduled"]
    assert "unscheduled" in preview["summary"].lower()


def test_smart_planner_project_filter_is_ownership_checked(app, client, user):
    from models import User
    with app.app_context():
        other = User(name="Other", email="other@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.flush()
        project = Project(user_id=other.id, title="Private project", status="In Progress", priority="Medium")
        db.session.add(project)
        db.session.commit()
        other_project_id = project.id

    _login(client)
    response = client.post(
        "/api/v1/planner/preview",
        json={"mode": "day", "project_id": other_project_id},
    )
    assert response.status_code == 400
    assert "not available" in response.get_json()["message"].lower()

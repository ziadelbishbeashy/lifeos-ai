from datetime import date, time, timedelta

from database import db
from models import (
    LearningModule,
    ModuleAssessment,
    Project,
    SmartPlannerBlock,
    SmartPlannerCommitment,
    SmartPlannerPlan,
    Task,
)


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
        deadline=date.today() + timedelta(days=5),
    )
    db.session.add(project)
    db.session.flush()
    tasks = [
        Task(
            user_id=user,
            project_id=project.id,
            title="Deploy backend",
            importance="Critical",
            difficulty="Medium",
            deadline=date.today(),
            status="Pending",
            priority_score=95,
        ),
        Task(
            user_id=user,
            project_id=project.id,
            title="Polish planner UI",
            importance="High",
            difficulty="Medium",
            deadline=date.today() + timedelta(days=2),
            status="Pending",
            priority_score=70,
        ),
        Task(
            user_id=user,
            project_id=project.id,
            title="Write beta notes",
            importance="Medium",
            difficulty="Easy",
            deadline=date.today() + timedelta(days=4),
            status="Pending",
            priority_score=45,
        ),
    ]
    db.session.add_all(tasks)
    db.session.commit()
    return project.id, [task.id for task in tasks]


def _accept_plan(client, project_id, *, mode="day", start=None):
    prepared = client.post(
        "/api/v1/planner/proposals",
        json={
            "mode": mode,
            "start_date": (start or date.today()).isoformat(),
            "working_start": "09:00",
            "working_end": "17:00",
            "break_minutes": 15,
            "project_id": project_id,
            "request_text": "Get V-SPACE ready",
        },
    )
    assert prepared.status_code == 201, prepared.get_json()
    proposal_id = prepared.get_json()["proposal"]["id"]
    confirmed = client.post(f"/api/v1/intelligence/action-proposals/{proposal_id}/confirm")
    assert confirmed.status_code == 200, confirmed.get_json()


def test_manual_commitment_blocks_time_in_preview(app, client, user):
    with app.app_context():
        project_id, _ = _workspace(user)
    _login(client)
    created = client.post(
        "/api/v1/planner/commitments",
        json={
            "title": "University class",
            "date": date.today().isoformat(),
            "start_time": "09:00",
            "end_time": "11:00",
            "commitment_type": "class",
        },
    )
    assert created.status_code == 201

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
    assert preview["days"][0]["commitments"][0]["title"] == "University class"
    assert preview["days"][0]["blocks"][0]["start_time"] >= "11:00"
    assert preview["commitment_minutes"] == 120


def test_timed_academic_assessment_is_read_only_fixed_commitment(app, client, user):
    with app.app_context():
        project_id, _ = _workspace(user)
        module = LearningModule(user_id=user, title="Calculus", status="Active")
        db.session.add(module)
        db.session.flush()
        db.session.add(ModuleAssessment(
            module_id=module.id,
            title="Midterm",
            assessment_type="Midterm",
            assessment_date=date.today(),
            assessment_time=time(10, 0),
            status="Upcoming",
        ))
        db.session.commit()

    _login(client)
    response = client.post(
        "/api/v1/planner/preview",
        json={
            "mode": "day",
            "start_date": date.today().isoformat(),
            "working_start": "09:00",
            "working_end": "17:00",
            "project_id": project_id,
        },
    )
    assert response.status_code == 200
    commitments = response.get_json()["preview"]["days"][0]["commitments"]
    academic = next(item for item in commitments if item["source"] == "academic")
    assert academic["title"] == "Midterm"
    assert academic["editable"] is False
    assert academic["module_title"] == "Calculus"


def test_upcoming_assessment_creates_preparation_blocks_before_exam(app, client, user):
    start = date.today()
    exam_day = start + timedelta(days=2)
    with app.app_context():
        project_id, _ = _workspace(user)
        module = LearningModule(user_id=user, title="Calculus", status="Active")
        db.session.add(module)
        db.session.flush()
        db.session.add(ModuleAssessment(
            module_id=module.id,
            title="Calculus Midterm",
            assessment_type="Midterm",
            assessment_date=exam_day,
            assessment_time=time(10, 0),
            estimated_study_minutes=180,
            topics="Integration, series",
            status="Upcoming",
        ))
        db.session.commit()

    _login(client)
    response = client.post(
        "/api/v1/planner/preview",
        json={
            "mode": "goal",
            "start_date": start.isoformat(),
            "horizon_days": 3,
            "working_start": "09:00",
            "working_end": "17:00",
            "break_minutes": 15,
            "project_id": project_id,
            "request_text": "Prepare for the next few days",
        },
    )

    assert response.status_code == 200, response.get_json()
    preview = response.get_json()["preview"]
    prep = [
        block
        for day in preview["days"]
        for block in day["blocks"]
        if block["block_type"] == "assessment_prep"
    ]
    assert prep
    assert sum(block["minutes"] for block in prep) == 180
    assert preview["assessment_prep_minutes"] == 180
    assert all(block["deadline"] == exam_day.isoformat() for block in prep)
    assert all(block["date"] <= exam_day.isoformat() for block in prep)

    exam_day_blocks = [block for block in prep if block["date"] == exam_day.isoformat()]
    assert all(block["end_time"] <= "10:00" for block in exam_day_blocks)

    commitments = [
        item
        for day in preview["days"]
        for item in day["commitments"]
        if item["source"] == "academic"
    ]
    assert any(item["title"] == "Calculus Midterm" for item in commitments)


def test_untimed_exam_does_not_guess_prep_can_happen_after_exam(app, client, user):
    start = date.today()
    exam_day = start + timedelta(days=1)
    with app.app_context():
        project_id, _ = _workspace(user)
        module = LearningModule(user_id=user, title="Physics", status="Active")
        db.session.add(module)
        db.session.flush()
        db.session.add(ModuleAssessment(
            module_id=module.id,
            title="Physics Quiz",
            assessment_type="Quiz",
            assessment_date=exam_day,
            assessment_time=None,
            estimated_study_minutes=60,
            status="Upcoming",
        ))
        db.session.commit()

    _login(client)
    response = client.post(
        "/api/v1/planner/preview",
        json={
            "mode": "goal",
            "start_date": start.isoformat(),
            "horizon_days": 2,
            "working_start": "09:00",
            "working_end": "17:00",
            "project_id": project_id,
            "request_text": "Plan my study time",
        },
    )

    assert response.status_code == 200, response.get_json()
    prep = [
        block
        for day in response.get_json()["preview"]["days"]
        for block in day["blocks"]
        if block["block_type"] == "assessment_prep"
    ]
    assert prep
    assert all(block["date"] < exam_day.isoformat() for block in prep)


def test_goal_mode_uses_requested_horizon(app, client, user):
    with app.app_context():
        project_id, _ = _workspace(user)
    _login(client)
    response = client.post(
        "/api/v1/planner/preview",
        json={
            "mode": "goal",
            "start_date": date.today().isoformat(),
            "horizon_days": 5,
            "working_start": "09:00",
            "working_end": "17:00",
            "project_id": project_id,
            "request_text": "Get V-SPACE ready for beta",
        },
    )
    assert response.status_code == 200
    preview = response.get_json()["preview"]
    assert preview["mode"] == "goal"
    assert preview["horizon_days"] == 5
    assert len(preview["days"]) == 5


def test_manual_block_edit_can_lock_block_and_rebalance_preserves_it(app, client, user):
    with app.app_context():
        project_id, _ = _workspace(user)
    _login(client)
    _accept_plan(client, project_id)

    with app.app_context():
        plan = SmartPlannerPlan.query.filter_by(user_id=user, status="accepted").one()
        block = plan.blocks[0]
        plan_id = plan.id
        block_id = block.id
        task_id = block.task_id

    edited = client.patch(
        f"/api/v1/planner/plans/{plan_id}/blocks/{block_id}",
        json={
            "date": date.today().isoformat(),
            "start_time": "14:00",
            "end_time": "15:00",
            "locked": True,
        },
    )
    assert edited.status_code == 200, edited.get_json()
    saved = next(item for item in edited.get_json()["plan"]["days"][0]["blocks"] if item["id"] == block_id)
    assert saved["locked"] is True
    assert saved["start_time"] == "14:00"

    rebalanced = client.post(
        f"/api/v1/planner/plans/{plan_id}/rebalance-preview",
        json={"from_date": date.today().isoformat()},
    )
    assert rebalanced.status_code == 200, rebalanced.get_json()
    preview = rebalanced.get_json()["preview"]
    preserved = next(item for item in preview["days"][0]["blocks"] if item["task_id"] == task_id)
    assert preserved["locked"] is True
    assert preserved["preserved"] is True
    assert preserved["start_time"] == "14:00"
    assert preview["rebalanced_from_plan_id"] == plan_id


def test_rebalance_requires_i9_confirmation_before_replacing_plan(app, client, user):
    with app.app_context():
        project_id, _ = _workspace(user)
    _login(client)
    _accept_plan(client, project_id)

    with app.app_context():
        original = SmartPlannerPlan.query.filter_by(user_id=user, status="accepted").one()
        original_id = original.id

    prepared = client.post(
        f"/api/v1/planner/plans/{original_id}/rebalance-proposals",
        json={"from_date": date.today().isoformat()},
    )
    assert prepared.status_code == 201, prepared.get_json()
    proposal = prepared.get_json()["proposal"]
    assert proposal["status"] == "pending"

    with app.app_context():
        assert SmartPlannerPlan.query.filter_by(user_id=user, status="accepted").one().id == original_id

    confirmed = client.post(f"/api/v1/intelligence/action-proposals/{proposal['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.get_json()
    with app.app_context():
        new_plan = SmartPlannerPlan.query.filter_by(user_id=user, status="accepted").one()
        assert new_plan.id != original_id
        assert new_plan.supersedes_plan_id == original_id
        assert SmartPlannerPlan.query.get(original_id).status == "superseded"


def test_completed_task_is_reflected_in_saved_plan_state(app, client, user):
    with app.app_context():
        project_id, task_ids = _workspace(user)
    _login(client)
    _accept_plan(client, project_id)

    with app.app_context():
        task = db.session.get(Task, task_ids[0])
        task.status = "Completed"
        db.session.commit()

    response = client.get(f"/api/v1/planner?date={date.today().isoformat()}")
    assert response.status_code == 200
    blocks = response.get_json()["planner"]["active_plan"]["days"][0]["blocks"]
    completed = next(item for item in blocks if item["task_id"] == task_ids[0])
    assert completed["state"] == "completed"
    assert completed["task_status"] == "Completed"


def test_manual_commitments_are_owner_scoped(app, client, user):
    with app.app_context():
        from models import User
        other = User(name="Other", email="planner-other@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.flush()
        row = SmartPlannerCommitment(
            user_id=other.id,
            title="Private meeting",
            commitment_date=date.today(),
            start_time=time(9, 0),
            end_time=time(10, 0),
            commitment_type="meeting",
        )
        db.session.add(row)
        db.session.commit()
        commitment_id = row.id

    _login(client)
    response = client.delete(f"/api/v1/planner/commitments/{commitment_id}")
    assert response.status_code == 400
    with app.app_context():
        assert db.session.get(SmartPlannerCommitment, commitment_id) is not None


def test_completed_assessment_prep_is_not_scheduled_again(app, client, user):
    start = date.today()
    exam_day = start + timedelta(days=2)
    with app.app_context():
        project_id, _ = _workspace(user)
        module = LearningModule(user_id=user, title="Calculus", status="Active")
        db.session.add(module)
        db.session.flush()
        assessment = ModuleAssessment(
            module_id=module.id,
            title="Calculus Midterm",
            assessment_type="Midterm",
            assessment_date=exam_day,
            assessment_time=time(10, 0),
            estimated_study_minutes=120,
            status="Upcoming",
        )
        db.session.add(assessment)
        db.session.commit()

    _login(client)
    prepared = client.post(
        "/api/v1/planner/proposals",
        json={
            "mode": "goal",
            "start_date": start.isoformat(),
            "horizon_days": 3,
            "working_start": "09:00",
            "working_end": "17:00",
            "break_minutes": 15,
            "project_id": project_id,
            "request_text": "Prepare for my assessment",
        },
    )
    assert prepared.status_code == 201, prepared.get_json()
    proposal_id = prepared.get_json()["proposal"]["id"]
    confirmed = client.post(f"/api/v1/intelligence/action-proposals/{proposal_id}/confirm")
    assert confirmed.status_code == 200, confirmed.get_json()

    with app.app_context():
        plan = SmartPlannerPlan.query.filter_by(user_id=user, status="accepted").one()
        prep_blocks = [b for b in plan.blocks if b.block_type == "assessment_prep"]
        assert prep_blocks
        prep_block_id = prep_blocks[0].id
        first_minutes = prep_blocks[0].minutes

    completed = client.patch(
        f"/api/v1/planner/plans/{plan.id}/blocks/{prep_block_id}",
        json={"completed": True},
    )
    assert completed.status_code == 200, completed.get_json()
    saved = next(
        block
        for day in completed.get_json()["plan"]["days"]
        for block in day["blocks"]
        if block["id"] == prep_block_id
    )
    assert saved["state"] == "completed"
    assert saved["completed_at"] is not None

    preview = client.post(
        "/api/v1/planner/preview",
        json={
            "mode": "goal",
            "start_date": start.isoformat(),
            "horizon_days": 3,
            "working_start": "09:00",
            "working_end": "17:00",
            "break_minutes": 15,
            "project_id": project_id,
            "request_text": "Prepare for my assessment",
        },
    )
    assert preview.status_code == 200, preview.get_json()
    remaining = [
        block
        for day in preview.get_json()["preview"]["days"]
        for block in day["blocks"]
        if block["block_type"] == "assessment_prep"
    ]
    assert sum(block["minutes"] for block in remaining) == 120 - first_minutes


def test_rebalance_does_not_recreate_completed_assessment_prep(app, client, user):
    start = date.today()
    exam_day = start + timedelta(days=2)
    with app.app_context():
        project_id, _ = _workspace(user)
        module = LearningModule(user_id=user, title="Physics", status="Active")
        db.session.add(module)
        db.session.flush()
        assessment = ModuleAssessment(
            module_id=module.id,
            title="Physics Final",
            assessment_type="Final",
            assessment_date=exam_day,
            assessment_time=time(14, 0),
            estimated_study_minutes=120,
            status="Upcoming",
        )
        db.session.add(assessment)
        db.session.commit()

    _login(client)
    prepared = client.post(
        "/api/v1/planner/proposals",
        json={
            "mode": "goal",
            "start_date": start.isoformat(),
            "horizon_days": 3,
            "working_start": "09:00",
            "working_end": "17:00",
            "break_minutes": 15,
            "project_id": project_id,
            "request_text": "Prepare for Physics",
        },
    )
    assert prepared.status_code == 201, prepared.get_json()
    proposal_id = prepared.get_json()["proposal"]["id"]
    assert client.post(f"/api/v1/intelligence/action-proposals/{proposal_id}/confirm").status_code == 200

    with app.app_context():
        plan = SmartPlannerPlan.query.filter_by(user_id=user, status="accepted").one()
        prep = next(b for b in plan.blocks if b.block_type == "assessment_prep")
        plan_id = plan.id
        prep_id = prep.id
        completed_minutes = prep.minutes

    assert client.patch(
        f"/api/v1/planner/plans/{plan_id}/blocks/{prep_id}",
        json={"completed": True},
    ).status_code == 200

    rebalanced = client.post(
        f"/api/v1/planner/plans/{plan_id}/rebalance-preview",
        json={"from_date": start.isoformat()},
    )
    assert rebalanced.status_code == 200, rebalanced.get_json()
    prep_blocks = [
        block
        for day in rebalanced.get_json()["preview"]["days"]
        for block in day["blocks"]
        if block["block_type"] == "assessment_prep"
    ]
    assert sum(block["minutes"] for block in prep_blocks) == 120 - completed_minutes

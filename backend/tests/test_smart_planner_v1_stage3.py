from datetime import date, timedelta, time

from database import db
from models import Project, SmartPlannerPlan, Task
from services.smart_planner_language_service import interpret_planner_request


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "StrongPass123!"},
    )
    assert response.status_code == 200


def _workspace(user, *, many=False):
    project = Project(
        user_id=user,
        title="V-SPACE V1",
        status="In Progress",
        priority="High",
        deadline=date.today() + timedelta(days=5),
    )
    db.session.add(project)
    db.session.flush()
    titles = [
        "Deploy backend",
        "Polish planner UI",
        "Write beta notes",
        "Review security",
        "Prepare onboarding",
        "Test document brain",
        "Check automations",
        "Finish launch checklist",
    ] if many else ["Deploy backend", "Polish planner UI", "Write beta notes"]
    tasks = []
    for index, title in enumerate(titles):
        tasks.append(Task(
            user_id=user,
            project_id=project.id,
            title=title,
            importance="Critical" if index == 0 else "High" if index < 3 else "Medium",
            difficulty="Medium",
            deadline=date.today() + timedelta(days=min(index, 4)),
            status="Pending",
            priority_score=max(25, 95 - index * 7),
        ))
    db.session.add_all(tasks)
    db.session.commit()
    return project.id


def test_language_parser_understands_core_v1_examples():
    anchor = date(2026, 9, 11)
    first = interpret_planner_request(
        "Tomorrow I have university until 2 PM, then I want 3 hours for V-SPACE and 90 minutes for calculus.",
        anchor_date=anchor,
    )
    assert first.mode == "day"
    assert first.start_date == date(2026, 9, 12)
    assert first.commitments[0].end_time.hour == 14
    assert [(item.title.lower(), item.minutes) for item in first.focus_requests] == [
        ("v-space", 180),
        ("calculus", 90),
    ]

    week = interpret_planner_request(
        "Plan my week around my classes and make sure I finish deployment before Friday.",
        anchor_date=anchor,
    )
    assert week.mode == "week"
    assert week.start_date is None
    assert "deployment" in [item.lower() for item in week.priority_terms]

    light = interpret_planner_request(
        "I'm tired today, give me a lighter plan and move the hard tasks to tomorrow.",
        anchor_date=anchor,
    )
    assert light.start_date == anchor
    assert light.energy_mode == "light"

    rebalance = interpret_planner_request(
        "I missed the morning. Replan the rest of today.",
        anchor_date=anchor,
    )
    assert rebalance.rebalance_requested is True
    assert rebalance.from_now is True


def test_natural_preview_blocks_interpreted_time_and_schedules_focus(app, client, user):
    with app.app_context():
        project_id = _workspace(user)
    _login(client)
    tomorrow = date.today() + timedelta(days=1)
    response = client.post(
        "/api/v1/planner/natural-preview",
        json={
            "mode": "day",
            "start_date": date.today().isoformat(),
            "working_start": "09:00",
            "working_end": "21:00",
            "break_minutes": 15,
            "project_id": project_id,
            "request_text": "Tomorrow I have university until 2 PM, then I want 3 hours for V-SPACE and 90 minutes for calculus.",
        },
    )
    assert response.status_code == 200, response.get_json()
    preview = response.get_json()["preview"]
    assert preview["start_date"] == tomorrow.isoformat()
    assert preview["interpretation"]["understood"] is True
    blocks = preview["days"][0]["blocks"]
    inferred = next(item for item in blocks if item["block_type"] == "inferred_commitment")
    assert inferred["start_time"] == "09:00"
    assert inferred["end_time"] == "14:00"
    assert inferred["locked"] is True
    focus = [item for item in blocks if item["block_type"] == "focus"]
    assert sum(item["minutes"] for item in focus if item["title"].lower() == "v-space") == 180
    assert sum(item["minutes"] for item in focus if item["title"].lower() == "calculus") == 90
    assert all(item["start_time"] >= "14:00" for item in blocks if item["block_type"] != "inferred_commitment")


def test_light_day_intentionally_reserves_capacity(app, client, user):
    with app.app_context():
        project_id = _workspace(user, many=True)
    _login(client)
    response = client.post(
        "/api/v1/planner/natural-preview",
        json={
            "mode": "day",
            "start_date": date.today().isoformat(),
            "working_start": "09:00",
            "working_end": "17:00",
            "break_minutes": 0,
            "project_id": project_id,
            "request_text": "I'm tired today, give me a lighter plan.",
        },
    )
    assert response.status_code == 200, response.get_json()
    preview = response.get_json()["preview"]
    assert preview["energy_mode"] == "light"
    assert preview["energy_reserve_minutes"] > 0
    assert preview["scheduled_minutes"] <= preview["available_minutes"]
    assert any("Light-day mode" in item["reason"] for item in preview["unscheduled"])


def test_natural_plan_stays_read_only_until_i9_confirmation_and_persists_prompt_blocks(app, client, user):
    with app.app_context():
        project_id = _workspace(user)
    _login(client)
    tomorrow = date.today() + timedelta(days=1)
    payload = {
        "mode": "day",
        "start_date": date.today().isoformat(),
        "working_start": "09:00",
        "working_end": "19:00",
        "break_minutes": 15,
        "project_id": project_id,
        "request_text": "Tomorrow I have university until 2 PM and I want 2 hours for V-SPACE.",
    }
    preview = client.post("/api/v1/planner/natural-preview", json=payload)
    assert preview.status_code == 200
    with app.app_context():
        assert SmartPlannerPlan.query.filter_by(user_id=user, status="accepted").count() == 0

    prepared = client.post("/api/v1/planner/natural-proposals", json=payload)
    assert prepared.status_code == 201, prepared.get_json()
    proposal = prepared.get_json()["proposal"]
    assert proposal["status"] == "pending"
    with app.app_context():
        assert SmartPlannerPlan.query.filter_by(user_id=user, status="accepted").count() == 0

    confirmed = client.post(f"/api/v1/intelligence/action-proposals/{proposal['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.get_json()
    with app.app_context():
        plan = SmartPlannerPlan.query.filter_by(user_id=user, status="accepted").one()
        assert plan.start_date == tomorrow
        inferred = next(block for block in plan.blocks if block.block_type == "inferred_commitment")
        assert inferred.locked is True
        assert inferred.start_time.hour == 9
        assert inferred.end_time.hour == 14
        focus = [block for block in plan.blocks if block.block_type == "focus"]
        assert sum(block.minutes for block in focus) == 120


def test_natural_preview_does_not_create_manual_commitments(app, client, user):
    from models import SmartPlannerCommitment

    with app.app_context():
        project_id = _workspace(user)
    _login(client)
    response = client.post(
        "/api/v1/planner/natural-preview",
        json={
            "mode": "day",
            "working_start": "09:00",
            "working_end": "18:00",
            "project_id": project_id,
            "request_text": "Tomorrow I have university until 2 PM then work on V-SPACE for 2 hours.",
        },
    )
    assert response.status_code == 200
    with app.app_context():
        assert SmartPlannerCommitment.query.filter_by(user_id=user).count() == 0


def test_language_parser_handles_ambiguous_daytime_and_do_not_overload():
    anchor = date(2026, 9, 12)
    parsed = interpret_planner_request(
        "Tomorrow I have university until 2, gym at 7, I need 3 hours on V-SPACE and calculus, but don't overload me.",
        anchor_date=anchor,
    )
    assert parsed.start_date == date(2026, 9, 13)
    assert parsed.mode == "day"
    assert parsed.energy_mode == "light"
    university = next(item for item in parsed.commitments if item.title == "University")
    assert university.start_time is None
    assert university.end_time.hour == 14
    gym = next(item for item in parsed.commitments if item.title == "Gym")
    assert gym.start_time.hour == 19
    assert gym.end_time.hour == 20
    assert gym.commitment_type == "personal"
    assert sum(item.minutes for item in parsed.focus_requests) == 180


def test_natural_preview_respects_university_until_two_without_meridiem(app, client, user):
    with app.app_context():
        project_id = _workspace(user, many=True)
    _login(client)
    tomorrow = date.today() + timedelta(days=1)
    response = client.post(
        "/api/v1/planner/natural-preview",
        json={
            "mode": "day",
            "working_start": "09:00",
            "working_end": "21:00",
            "break_minutes": 15,
            "project_id": project_id,
            "request_text": "Tomorrow I have university until 2, gym at 7, I need 3 hours on V-SPACE and calculus, but don't overload me.",
        },
    )
    assert response.status_code == 200, response.get_json()
    preview = response.get_json()["preview"]
    assert preview["start_date"] == tomorrow.isoformat()
    assert preview["energy_mode"] == "light"
    assert preview["title"].startswith("Tomorrow plan")
    blocks = preview["days"][0]["blocks"]
    university = next(item for item in blocks if item["block_type"] == "inferred_commitment" and item["title"] == "University")
    assert university["start_time"] == "09:00"
    assert university["end_time"] == "14:00"
    gym = next(item for item in blocks if item["block_type"] == "inferred_commitment" and item["title"] == "Gym")
    assert gym["start_time"] == "19:00"
    assert gym["end_time"] == "20:00"
    assert all(item["start_time"] >= "14:00" for item in blocks if item["block_type"] != "inferred_commitment")
    assert preview["overload_minutes"] == 0
    assert preview["deferred_minutes"] > 0


def test_language_parser_understands_spoken_dayparts_and_flags_risky_ambiguity():
    anchor = date(2026, 9, 12)
    parsed = interpret_planner_request(
        "Tomorrow I have class from 9 in the morning to 2 in the afternoon, then a meeting at 10 at night.",
        anchor_date=anchor,
    )
    class_block = next(item for item in parsed.commitments if item.title == "Class")
    meeting = next(item for item in parsed.commitments if item.title == "Meeting")
    assert class_block.start_time.hour == 9
    assert class_block.end_time.hour == 14
    assert meeting.start_time.hour == 22
    assert any("9:00 AM" in note and "2:00 PM" in note for note in parsed.assumptions)

    ambiguous = interpret_planner_request("Tomorrow I have gym at 10.", anchor_date=anchor)
    assert ambiguous.commitments == ()
    assert ambiguous.clarifications
    assert "10:00 AM" in ambiguous.clarifications[0]
    assert "10:00 PM" in ambiguous.clarifications[0]

    personalized = interpret_planner_request(
        "Tomorrow I have gym at 10.",
        anchor_date=anchor,
        known_activity_times={"gym": time(19, 0)},
    )
    gym = next(item for item in personalized.commitments if item.title == "Gym")
    assert gym.start_time.hour == 22
    assert not personalized.clarifications

    with_duration = interpret_planner_request(
        "Tomorrow I have gym at 10 at night.",
        anchor_date=anchor,
        known_activity_times={"gym": {"start_time": time(19, 0), "duration_minutes": 90}},
    )
    gym = next(item for item in with_duration.commitments if item.title == "Gym")
    assert gym.start_time.hour == 22
    assert gym.end_time.hour == 23 and gym.end_time.minute == 30

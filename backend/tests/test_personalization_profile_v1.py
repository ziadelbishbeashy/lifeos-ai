from datetime import date, timedelta

from database import db
from models import Project, Task, UserPersonalizationProfile


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "StrongPass123!"},
    )
    assert response.status_code == 200


def _task(user_id: int):
    project = Project(user_id=user_id, title="Personalization test", status="In Progress", priority="High")
    db.session.add(project)
    db.session.flush()
    db.session.add(Task(
        user_id=user_id,
        project_id=project.id,
        title="Important work",
        importance="High",
        difficulty="Medium",
        status="Pending",
        priority_score=80,
        deadline=date.today() + timedelta(days=1),
    ))
    db.session.commit()
    return project.id


def test_missing_profile_is_read_only_and_first_login_summary_is_not_started(app, client, user):
    _login(client)
    response = client.get("/api/v1/session")
    assert response.status_code == 200
    summary = response.get_json()["user"]["personalization"]
    assert summary["onboarding_state"] == "not_started"
    assert summary["answered_count"] == 0
    assert summary["total_questions"] == 7
    with app.app_context():
        assert UserPersonalizationProfile.query.filter_by(user_id=user).count() == 0


def test_user_can_defer_without_being_prompted_every_login(app, client, user):
    _login(client)
    response = client.post("/api/v1/personalization/defer", json={})
    assert response.status_code == 200
    assert response.get_json()["personalization"]["onboarding_state"] == "deferred"
    session = client.get("/api/v1/session").get_json()
    assert session["user"]["personalization"]["deferred"] is True
    with app.app_context():
        profile = UserPersonalizationProfile.query.filter_by(user_id=user).one()
        assert profile.deferred_at is not None


def test_profile_validation_and_private_serialization(app, client, user):
    _login(client)
    weekday = date.today().weekday()
    response = client.patch("/api/v1/personalization", json={
        "usual_wake_time": "08:00",
        "usual_sleep_time": "00:30",
        "productive_period": "evening",
        "preferred_focus_minutes": 60,
        "preferred_break_minutes": 20,
        "planning_intensity": "balanced",
        "workday_start": "10:00",
        "workday_end": "21:00",
        "avoid_after_time": "22:30",
        "regular_commitments": [{
            "title": "Gym",
            "days": [weekday],
            "start_time": "19:00",
            "end_time": "20:30",
            "commitment_type": "gym",
        }],
        "priorities": ["university", "projects", "fitness"],
        "overload_behavior": "leave_unscheduled",
    })
    assert response.status_code == 200, response.get_json()
    profile = response.get_json()["personalization"]
    assert profile["completed"] is True
    assert profile["usual_wake_time"] == "08:00"
    assert profile["regular_commitments"][0]["title"] == "Gym"
    assert profile["privacy"]["web_search_excluded"] is True
    assert "Smart Planner" in profile["usage"]["regular_commitments"]
    with app.app_context():
        row = UserPersonalizationProfile.query.filter_by(user_id=user).one()
        assert row.user_id == user
        assert row.data_use_acknowledged_at is not None


def test_planner_uses_profile_defaults_and_recurring_commitments_but_explicit_controls_win(app, client, user):
    with app.app_context():
        project_id = _task(user)
    _login(client)
    weekday = date.today().weekday()
    saved = client.patch("/api/v1/personalization", json={
        "preferred_break_minutes": 20,
        "planning_intensity": "light",
        "workday_start": "10:00",
        "workday_end": "21:00",
        "regular_commitments": [{
            "title": "Gym",
            "days": [weekday],
            "start_time": "19:00",
            "end_time": "20:30",
            "commitment_type": "gym",
        }],
        "overload_behavior": "leave_unscheduled",
    })
    assert saved.status_code == 200, saved.get_json()

    state = client.get(f"/api/v1/planner?date={date.today().isoformat()}")
    assert state.status_code == 200
    planner = state.get_json()["planner"]
    assert planner["defaults"]["working_start"] == "10:00"
    assert planner["defaults"]["working_end"] == "21:00"
    assert planner["defaults"]["break_minutes"] == 20
    assert planner["defaults"]["energy_mode"] == "light"
    routine = [item for item in planner["commitments"] if item["source"] == "profile"]
    today_routine = [item for item in routine if item["date"] == date.today().isoformat()]
    assert len(today_routine) == 1
    assert today_routine[0]["title"] == "Gym"
    assert today_routine[0]["start_time"] == "19:00"
    assert today_routine[0]["end_time"] == "20:30"

    # Planner state intentionally exposes a 14-day commitment window, so a
    # weekly profile commitment should also recur on the same weekday next week.
    next_week = (date.today() + timedelta(days=7)).isoformat()
    assert any(
        item["title"] == "Gym" and item["date"] == next_week
        for item in routine
    )

    preview = client.post("/api/v1/planner/preview", json={
        "mode": "day",
        "start_date": date.today().isoformat(),
        "project_id": project_id,
    })
    assert preview.status_code == 200, preview.get_json()
    plan = preview.get_json()["preview"]
    assert plan["working_start"] == "10:00"
    assert plan["working_end"] == "21:00"
    assert plan["break_minutes"] == 20
    assert plan["energy_mode"] == "light"
    assert plan["planning_defaults"]["profile_applied"] is True

    explicit = client.post("/api/v1/planner/preview", json={
        "mode": "day",
        "start_date": date.today().isoformat(),
        "working_start": "08:00",
        "working_end": "18:00",
        "break_minutes": 5,
        "project_id": project_id,
    })
    assert explicit.status_code == 200, explicit.get_json()
    explicit_plan = explicit.get_json()["preview"]
    assert explicit_plan["working_start"] == "08:00"
    assert explicit_plan["working_end"] == "18:00"
    assert explicit_plan["break_minutes"] == 5


def test_prompt_commitment_overrides_same_profile_routine_for_that_preview(app, client, user):
    with app.app_context():
        project_id = _task(user)
    _login(client)
    tomorrow = date.today() + timedelta(days=1)
    saved = client.patch("/api/v1/personalization", json={
        "workday_start": "09:00",
        "workday_end": "22:00",
        "regular_commitments": [{
            "title": "Gym",
            "days": [tomorrow.weekday()],
            "start_time": "19:00",
            "end_time": "20:30",
            "commitment_type": "gym",
        }],
    })
    assert saved.status_code == 200
    response = client.post("/api/v1/planner/natural-preview", json={
        "mode": "day",
        "start_date": date.today().isoformat(),
        "project_id": project_id,
        "request_text": "Tomorrow I have gym at 8 PM and need to work on my project.",
    })
    assert response.status_code == 200, response.get_json()
    preview = response.get_json()["preview"]
    day = preview["days"][0]
    assert not [item for item in day["commitments"] if item["source"] == "profile" and item["title"] == "Gym"]
    inferred = [item for item in day["blocks"] if item["block_type"] == "inferred_commitment" and item["title"] == "Gym"]
    assert len(inferred) == 1
    assert inferred[0]["start_time"] == "20:00"
    # The explicit start time wins, while the saved 90-minute gym duration is
    # reused because the user did not provide a different duration today.
    assert inferred[0]["end_time"] == "21:30"


def test_clearing_profile_keeps_account_data_but_returns_to_visible_defaults(app, client, user):
    _login(client)
    assert client.patch("/api/v1/personalization", json={"workday_start": "11:00", "workday_end": "20:00"}).status_code == 200
    cleared = client.delete("/api/v1/personalization")
    assert cleared.status_code == 200
    profile = cleared.get_json()["personalization"]
    assert profile["onboarding_state"] == "deferred"
    assert profile["workday_start"] is None
    planner = client.get("/api/v1/planner").get_json()["planner"]
    assert planner["defaults"]["working_start"] == "09:00"
    assert planner["defaults"]["working_end"] == "17:00"


def test_profile_changes_real_planner_capacity_and_peak_placement(app, client, user):
    with app.app_context():
        project_id = _task(user)
        # Enough work to fill the physical window, so the test proves the
        # profile capacity preference actually changes scheduling behavior.
        db.session.add_all([
            Task(
                user_id=user, project_id=project_id, title=f"Extra work {index}",
                importance="Medium", difficulty="Hard", status="Pending",
                priority_score=50 - index, deadline=date.today() + timedelta(days=3),
            )
            for index in range(1, 12)
        ])
        db.session.commit()
    _login(client)
    saved = client.patch("/api/v1/personalization", json={
        "usual_wake_time": "08:00",
        "usual_sleep_time": "01:00",
        "productive_period": "evening",
        "preferred_focus_minutes": 60,
        "preferred_break_minutes": 20,
        "planning_intensity": "balanced",
        "overload_behavior": "leave_unscheduled",
    })
    assert saved.status_code == 200, saved.get_json()

    state = client.get(f"/api/v1/planner?date={date.today().isoformat()}").get_json()["planner"]
    assert state["defaults"]["working_start"] == "08:30"
    assert state["defaults"]["working_end"] == "23:30"
    assert state["defaults"]["productive_period"] == "evening"
    assert state["defaults"]["preferred_focus_minutes"] == 60
    assert state["defaults"]["capacity_factor"] == 0.80

    response = client.post("/api/v1/planner/preview", json={
        "mode": "day",
        "start_date": date.today().isoformat(),
        "project_id": project_id,
    })
    assert response.status_code == 200, response.get_json()
    preview = response.get_json()["preview"]
    # The scheduler prioritizes the most important work inside the user's peak
    # window first. Lower-priority overflow may still use other available hours,
    # so checking the earliest chronological block would be incorrect.
    important_block = next(
        item for item in preview["days"][0]["blocks"]
        if item["block_type"] == "task" and item["title"] == "Important work"
    )
    assert important_block["start_time"] >= "17:00"
    assert "evening focus preference" in (important_block["rationale"] or "")
    assert preview["planning_defaults"]["profile_applied"] is True
    assert preview["planning_defaults"]["reasons"]
    assert preview["energy_reserve_minutes"] > 0
    assert preview["deferred_minutes"] > 0
    assert any(item.get("source") == "capacity_preference" for item in preview["unscheduled"])

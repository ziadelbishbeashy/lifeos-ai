from __future__ import annotations

from datetime import date, datetime, timedelta

from database import db
from models import (
    LifeOSIntelligenceEvent,
    LifeOSProactiveNotification,
    Project,
    Task,
    User,
)
from services.intelligence_event_service import scan_owned_intelligence_events
from services.lifeos_activity_service import add_activity_event
from services.proactive_intelligence_service import (
    dismiss_owned_proactive_notification,
    list_owned_proactive_notifications,
    mark_owned_proactive_notification_read,
    refresh_owned_proactive_notifications,
)


def _project(user_id: int, title: str = "LifeOS") -> Project:
    project = Project(
        user_id=user_id,
        title=title,
        status="In Progress",
        priority="Medium",
        progress=20,
    )
    db.session.add(project)
    db.session.commit()
    return project


def _login(client):
    return client.post(
        "/login",
        data={"email": "student@example.com", "password": "StrongPass123!"},
        follow_redirects=False,
    )


def test_i14_detects_overdue_blocked_and_approaching_events_idempotently(app, user):
    with app.app_context():
        project = _project(user)
        db.session.add_all([
            Task(
                user_id=user,
                project_id=project.id,
                title="Overdue checkout fix",
                status="Pending",
                deadline=date.today() - timedelta(days=2),
            ),
            Task(
                user_id=user,
                project_id=project.id,
                title="Blocked auth review",
                status="Blocked",
            ),
            Task(
                user_id=user,
                project_id=project.id,
                title="Due tomorrow",
                status="Pending",
                deadline=date.today() + timedelta(days=1),
            ),
        ])
        db.session.commit()

        first = scan_owned_intelligence_events(owner_id=user)
        types = {event.event_type for event in first.events}
        assert "task.overdue" in types
        assert "task.blocked" in types
        assert "deadline.approaching" in types
        count = LifeOSIntelligenceEvent.query.filter_by(user_id=user).count()

        second = scan_owned_intelligence_events(owner_id=user)
        assert LifeOSIntelligenceEvent.query.filter_by(user_id=user).count() == count
        assert second.open_count >= 3
        assert second.to_dict()["read_only_workspace"] is True


def test_i14_date_only_deadlines_use_local_calendar_even_when_scan_timestamp_is_previous_utc_day(app, user):
    """Regression: local midnight must not downgrade yesterday's task to due today."""
    with app.app_context():
        project = _project(user)
        task = Task(
            user_id=user,
            project_id=project.id,
            title="Local-midnight overdue task",
            status="Pending",
            deadline=date.today() - timedelta(days=1),
        )
        db.session.add(task)
        db.session.commit()

        previous_utc_day = datetime.combine(date.today() - timedelta(days=1), datetime.max.time())
        result = scan_owned_intelligence_events(owner_id=user, now=previous_utc_day)
        types = {event.event_type for event in result.events}

        assert "task.overdue" in types
        assert not any(
            event.event_type == "deadline.approaching" and event.object_id == task.id
            for event in result.events
        )


def test_i14_resolves_state_event_when_condition_is_no_longer_true(app, user):
    with app.app_context():
        project = _project(user)
        task = Task(
            user_id=user,
            project_id=project.id,
            title="Temporary blocker",
            status="Blocked",
        )
        db.session.add(task)
        db.session.commit()

        scan_owned_intelligence_events(owner_id=user)
        event = LifeOSIntelligenceEvent.query.filter_by(user_id=user, event_type="task.blocked").one()
        assert event.lifecycle == "open"

        task.status = "Pending"
        db.session.commit()
        scan_owned_intelligence_events(owner_id=user)
        db.session.refresh(event)
        assert event.lifecycle == "resolved"
        assert event.resolved_at is not None


def test_i14_normalizes_recent_i10_activity(app, user):
    with app.app_context():
        project = _project(user)
        add_activity_event(
            user_id=user,
            event_type="document.version_changed",
            object_type="document",
            object_id=44,
            project_id=project.id,
            title="Document version changed: Plan.pdf",
            summary="A new current version was uploaded.",
            created_at=datetime.utcnow() - timedelta(minutes=5),
        )
        db.session.commit()

        result = scan_owned_intelligence_events(owner_id=user)
        event = next(item for item in result.events if item.event_type == "document.version_changed")
        assert event.lifecycle == "observed"
        assert event.source_type == "activity"
        assert event.project_id == project.id


def test_i15_materializes_notice_once_and_never_changes_workspace_task(app, user):
    with app.app_context():
        project = _project(user)
        task = Task(
            user_id=user,
            project_id=project.id,
            title="Overdue launch task",
            status="Pending",
            deadline=date.today() - timedelta(days=1),
        )
        db.session.add(task)
        db.session.commit()
        before = (task.status, task.deadline, Task.query.filter_by(user_id=user).count())

        first = refresh_owned_proactive_notifications(owner_id=user)
        assert first.unread_count >= 1
        notice = next(item for item in first.items if item.event.event_type == "task.overdue")
        assert notice.status == "unread"
        assert notice.action_href == "/tasks"

        refresh_owned_proactive_notifications(owner_id=user)
        assert LifeOSProactiveNotification.query.filter_by(user_id=user, event_id=notice.event_id).count() == 1
        after = (task.status, task.deadline, Task.query.filter_by(user_id=user).count())
        assert after == before


def test_i15_read_dismiss_and_owner_isolation(app, user):
    with app.app_context():
        project = _project(user)
        db.session.add(Task(
            user_id=user,
            project_id=project.id,
            title="Overdue private task",
            status="Pending",
            deadline=date.today() - timedelta(days=1),
        ))
        other = User(name="Other", email="i15-other@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()

        refresh = refresh_owned_proactive_notifications(owner_id=user)
        notice = next(item for item in refresh.items if item.event.event_type == "task.overdue")
        mark_owned_proactive_notification_read(owner_id=user, notification_id=notice.id)
        assert notice.status == "read"
        dismiss_owned_proactive_notification(owner_id=user, notification_id=notice.id)
        assert notice.status == "dismissed"

        hidden = list_owned_proactive_notifications(owner_id=other.id)
        assert hidden.items == ()
        assert hidden.unread_count == 0


def test_i15_api_refresh_exposes_only_authenticated_owner_and_unread_badge_count(client, app, user):
    with app.app_context():
        own = _project(user, "Visible")
        db.session.add(Task(
            user_id=user,
            project_id=own.id,
            title="Visible overdue",
            status="Pending",
            deadline=date.today() - timedelta(days=1),
        ))
        other = User(name="Other", email="i15-api-other@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.flush()
        hidden = _project(other.id, "Hidden")
        db.session.add(Task(
            user_id=other.id,
            project_id=hidden.id,
            title="Hidden overdue",
            status="Pending",
            deadline=date.today() - timedelta(days=5),
        ))
        db.session.commit()

    _login(client)
    response = client.post("/api/v1/intelligence/proactive/refresh", json={})
    assert response.status_code == 200
    payload = response.get_json()["proactive"]
    assert payload["verified_from_state"] is True
    assert payload["workspace_mutation"] is False
    assert payload["counts"]["unread"] >= 1
    raw = str(payload)
    assert "Visible overdue" in raw
    assert "Hidden overdue" not in raw

from __future__ import annotations

from datetime import date, datetime, timedelta

from database import db
from models import (
    LifeOSAutomationRun,
    LifeOSIntelligenceEvent,
    LifeOSProactiveNotification,
    Project,
    Task,
)
from services.automation_engine_service import (
    execute_owned_automation,
    execute_owned_automation_cycle,
)
from services.automation_service import automation_registry, create_owned_automation


def _project(user_id: int, title: str = "LifeOS") -> Project:
    item = Project(user_id=user_id, title=title, status="In Progress", priority="Medium", progress=20)
    db.session.add(item)
    db.session.commit()
    return item


def test_i17_activation_templates_automate_intelligence_not_duplicate_basic_reminders():
    registry = automation_registry()
    keys = {item["key"] for item in registry["templates"]}
    assert keys == {"morning_briefing", "weekly_review", "risk_escalation", "unhandled_followup"}
    assert "overdue_watch" not in keys
    assert "stale_document_watch" not in keys
    assert registry["safety"]["background_execution_available"] is True
    assert registry["safety"]["workspace_mutation"] is False


def test_i17_manual_execution_delivers_briefing_without_workspace_mutation(app, user):
    with app.app_context():
        project = _project(user)
        task = Task(
            user_id=user,
            project_id=project.id,
            title="Keep workspace unchanged",
            status="Pending",
            importance="Medium",
            difficulty="Medium",
        )
        db.session.add(task)
        db.session.commit()
        before = (Task.query.filter_by(user_id=user).count(), task.status, task.deadline)

        automation = create_owned_automation(
            owner_id=user,
            name="Morning intelligence briefing",
            trigger_type="schedule_daily",
            trigger_config={"hour": 8, "minute": 0},
            action_type="today_briefing",
            action_config={},
            timezone_name="UTC",
        )
        result = execute_owned_automation(
            owner_id=user,
            automation_id=automation.id,
            trigger_source="manual",
        )

        db.session.refresh(task)
        after = (Task.query.filter_by(user_id=user).count(), task.status, task.deadline)
        assert before == after
        assert result.run.status == "succeeded"
        assert result.run.dry_run is False
        assert result.output["kind"] == "today_briefing"
        assert result.output["verified_from_state"] is True
        assert result.notification_event_id is not None
        assert LifeOSAutomationRun.query.filter_by(user_id=user, automation_id=automation.id, dry_run=False).count() == 1
        assert LifeOSProactiveNotification.query.filter_by(user_id=user, event_id=result.notification_event_id).count() == 1


def test_i17_due_schedule_executes_once_and_advances_next_run(app, user):
    with app.app_context():
        automation = create_owned_automation(
            owner_id=user,
            name="Scheduled daily intelligence",
            enabled=True,
            trigger_type="schedule_daily",
            trigger_config={"hour": 8, "minute": 0},
            action_type="today_briefing",
            action_config={},
            timezone_name="UTC",
        )
        now = datetime(2026, 8, 30, 12, 0)
        automation.next_run_at = now - timedelta(minutes=1)
        db.session.commit()

        first = execute_owned_automation_cycle(owner_id=user, now=now)
        matching = [item for item in first.results if item.automation_id == automation.id]
        assert len(matching) == 1
        db.session.refresh(automation)
        assert automation.last_run_at is not None
        assert automation.next_run_at is not None
        assert automation.next_run_at > now

        second = execute_owned_automation_cycle(owner_id=user, now=now)
        assert not any(item.automation_id == automation.id for item in second.results)


def test_i17_event_rule_reviews_context_and_consumes_verified_event_once(app, user):
    with app.app_context():
        project = _project(user)
        db.session.add(Task(
            user_id=user,
            project_id=project.id,
            title="Overdue launch task",
            status="Pending",
            importance="High",
            difficulty="Medium",
            deadline=date.today() - timedelta(days=1),
        ))
        automation = create_owned_automation(
            owner_id=user,
            name="Contextual overdue review",
            enabled=True,
            trigger_type="event",
            trigger_config={"event_type": "task.overdue"},
            action_type="attention_notice",
            action_config={},
            timezone_name="UTC",
        )
        db.session.commit()

        first = execute_owned_automation_cycle(owner_id=user)
        matched = [item for item in first.results if item.automation_id == automation.id]
        assert len(matched) == 1
        db.session.refresh(automation)
        assert automation.last_event_id is not None
        assert matched[0].output["kind"] == "event_context_review"
        assert LifeOSIntelligenceEvent.query.filter_by(
            user_id=user,
            event_type="automation.event_context_ready",
            source_type="automation",
        ).count() == 1

        second = execute_owned_automation_cycle(owner_id=user)
        assert not any(item.automation_id == automation.id for item in second.results)


def test_i17_risk_escalation_requires_compound_signal_before_notification(app, user):
    with app.app_context():
        project = _project(user)
        db.session.add(Task(
            user_id=user,
            project_id=project.id,
            title="Only overdue item",
            status="Pending",
            importance="High",
            difficulty="Medium",
            deadline=date.today() - timedelta(days=1),
        ))
        db.session.commit()
        automation = create_owned_automation(
            owner_id=user,
            name="Risk escalation",
            trigger_type="schedule_daily",
            trigger_config={"hour": 17, "minute": 30},
            action_type="risk_escalation",
            action_config={},
            timezone_name="UTC",
        )
        first = execute_owned_automation(owner_id=user, automation_id=automation.id)
        assert first.output["kind"] == "risk_escalation"
        assert first.output["notification"]["should_notify"] is False
        assert first.notification_event_id is None

        db.session.add(Task(
            user_id=user,
            project_id=project.id,
            title="Blocked integration",
            status="Blocked",
            importance="High",
            difficulty="Medium",
        ))
        db.session.commit()
        second = execute_owned_automation(owner_id=user, automation_id=automation.id)
        assert second.output["notification"]["should_notify"] is True
        assert second.output["escalations"]
        assert second.notification_event_id is not None

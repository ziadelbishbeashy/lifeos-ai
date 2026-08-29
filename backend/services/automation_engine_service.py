"""I17 automation engine — real, read-only intelligence execution.

The engine executes only allow-listed LifeOS intelligence actions.  It may write
its own audit/run rows plus I14/I15 delivery metadata, but it never writes user
workspace resources (Project/Task/Note/Document/etc.).  Any future workspace
mutation must still be proposed and confirmed through I9.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any

from database import db
from models import LifeOSAutomation, LifeOSAutomationRun, LifeOSIntelligenceEvent
from services.automation_service import (
    AutomationNotFoundError,
    AutomationValidationError,
    automation_run_to_dict,
    build_owned_automation_output,
    calculate_next_run_at,
    due_owned_schedule_automations,
    event_matches_automation,
)
from services.intelligence_event_service import scan_owned_intelligence_events
from services.proactive_intelligence_service import refresh_owned_proactive_notifications


@dataclass(frozen=True)
class AutomationCandidate:
    automation_id: int
    automation_name: str
    trigger_source: str
    event_id: int | None = None
    event_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "automation_id": self.automation_id,
            "automation_name": self.automation_name,
            "trigger_source": self.trigger_source,
            "event_id": self.event_id,
            "event_type": self.event_type,
        }


@dataclass(frozen=True)
class AutomationPreparationCycle:
    owner_id: int
    candidates: tuple[AutomationCandidate, ...]
    scanned_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner_id": self.owner_id,
            "candidates": [item.to_dict() for item in self.candidates],
            "counts": {
                "total": len(self.candidates),
                "scheduled": sum(1 for item in self.candidates if item.trigger_source == "schedule"),
                "event": sum(1 for item in self.candidates if item.trigger_source == "event"),
            },
            "scanned_at": self.scanned_at.isoformat(),
            "preparation_mode": False,
            "actions_executed": 0,
            "workspace_mutation": False,
        }


@dataclass(frozen=True)
class AutomationExecutionResult:
    automation_id: int
    run: LifeOSAutomationRun
    output: dict[str, Any]
    notification_event_id: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "automation_id": self.automation_id,
            "run": automation_run_to_dict(self.run),
            "output": self.output,
            "notification_event_id": self.notification_event_id,
            "verified_from_state": True,
            "workspace_mutation": False,
            "execution_mode": "automation",
        }


@dataclass(frozen=True)
class AutomationExecutionCycle:
    owner_id: int
    candidates: tuple[AutomationCandidate, ...]
    results: tuple[AutomationExecutionResult, ...]
    failures: tuple[dict[str, Any], ...]
    scanned_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner_id": self.owner_id,
            "candidates": [item.to_dict() for item in self.candidates],
            "runs": [item.to_dict() for item in self.results],
            "failures": list(self.failures),
            "counts": {
                "candidates": len(self.candidates),
                "executed": len(self.results),
                "failed": len(self.failures),
                "notifications_prepared": sum(1 for item in self.results if item.notification_event_id is not None),
            },
            "scanned_at": self.scanned_at.isoformat(),
            "verified_from_state": True,
            "workspace_mutation": False,
        }


def collect_owned_automation_candidates(*, owner_id: int, now: datetime | None = None) -> AutomationPreparationCycle:
    effective_now = now or datetime.utcnow()
    # Keep I14 current before matching event-driven rules. I14 itself does not
    # mutate user workspace resources.
    scan_owned_intelligence_events(owner_id=owner_id, now=effective_now)

    candidates: list[AutomationCandidate] = []
    for automation in due_owned_schedule_automations(owner_id=owner_id, now=effective_now):
        candidates.append(AutomationCandidate(
            automation_id=automation.id,
            automation_name=automation.name,
            trigger_source="schedule",
        ))

    event_automations = LifeOSAutomation.query.filter_by(
        user_id=owner_id,
        enabled=True,
        trigger_type="event",
    ).all()
    if event_automations:
        events = LifeOSIntelligenceEvent.query.filter_by(user_id=owner_id).order_by(
            LifeOSIntelligenceEvent.id.asc()
        ).all()
        for automation in event_automations:
            last_seen = int(automation.last_event_id or 0)
            for event in events:
                if int(event.id or 0) <= last_seen:
                    continue
                if event_matches_automation(automation, event):
                    candidates.append(AutomationCandidate(
                        automation_id=automation.id,
                        automation_name=automation.name,
                        trigger_source="event",
                        event_id=event.id,
                        event_type=event.event_type,
                    ))

    return AutomationPreparationCycle(
        owner_id=owner_id,
        candidates=tuple(candidates),
        scanned_at=effective_now,
    )


def _owned_automation(*, owner_id: int, automation_id: int) -> LifeOSAutomation:
    item = LifeOSAutomation.query.filter_by(id=int(automation_id), user_id=int(owner_id)).first()
    if item is None:
        raise AutomationNotFoundError("Automation not found.")
    return item


def _notification_event(
    *,
    owner_id: int,
    automation: LifeOSAutomation,
    run: LifeOSAutomationRun,
    output: dict[str, Any],
    now: datetime,
) -> LifeOSIntelligenceEvent | None:
    notification = output.get("notification") if isinstance(output, dict) else None
    if not isinstance(notification, dict) or not bool(notification.get("should_notify")):
        return None

    event_type = str(notification.get("event_type") or "automation.result_ready")[:80]
    dedupe_scope = str(notification.get("dedupe_scope") or "run")[:160]
    if dedupe_scope == "run":
        dedupe_key = f"automation:{automation.id}:run:{run.id}:{event_type}"
    else:
        dedupe_key = f"automation:{automation.id}:{event_type}:{dedupe_scope}"
    dedupe_key = dedupe_key[:255]

    event = LifeOSIntelligenceEvent.query.filter_by(user_id=owner_id, dedupe_key=dedupe_key).first()
    if event is None:
        event = LifeOSIntelligenceEvent(
            user_id=owner_id,
            dedupe_key=dedupe_key,
            detected_at=now,
        )
        db.session.add(event)

    severity = str(notification.get("severity") or "info").strip().casefold()
    if severity not in {"info", "normal", "medium", "high", "critical"}:
        severity = "normal"
    project_id = output.get("project_id")
    try:
        project_id = int(project_id) if project_id is not None else None
    except (TypeError, ValueError):
        project_id = None

    event.event_type = event_type
    event.severity = severity
    event.lifecycle = "observed"
    event.object_type = "automation"
    event.object_id = automation.id
    event.project_id = project_id
    event.title = " ".join(str(notification.get("title") or automation.name).split())[:255]
    event.summary = " ".join(str(notification.get("message") or output.get("summary") or "Automation completed.").split())[:2000]
    event.context_json = json.dumps({
        "automation_id": automation.id,
        "automation_name": automation.name,
        "automation_run_id": run.id,
        "output_kind": output.get("kind"),
        "action_label": notification.get("action_label"),
        "action_href": notification.get("action_href"),
        "ask_query": notification.get("ask_query"),
        "verified_from_state": True,
        "workspace_mutation": False,
    }, ensure_ascii=False, sort_keys=True)
    event.source_type = "automation"
    event.source_id = run.id
    event.last_seen_at = now
    event.resolved_at = None
    db.session.flush()
    return event


def execute_owned_automation(
    *,
    owner_id: int,
    automation_id: int,
    trigger_source: str = "manual",
    event_id: int | None = None,
    now: datetime | None = None,
) -> AutomationExecutionResult:
    """Execute one allow-listed read-only automation and persist its audit row."""

    effective_now = now or datetime.utcnow()
    automation = _owned_automation(owner_id=owner_id, automation_id=automation_id)
    source = str(trigger_source or "manual").strip().casefold()
    if source not in {"manual", "schedule", "event"}:
        raise AutomationValidationError("Unsupported automation trigger source.")

    if source == "event":
        if event_id is None:
            raise AutomationValidationError("An event-triggered automation requires the verified I14 event id.")
        event = LifeOSIntelligenceEvent.query.filter_by(id=int(event_id), user_id=owner_id).first()
        if event is None or not event_matches_automation(automation, event):
            raise AutomationValidationError("The event does not match this automation trigger.")

    run = LifeOSAutomationRun(
        automation_id=automation.id,
        user_id=owner_id,
        status="running",
        trigger_source=source,
        event_id=int(event_id) if event_id is not None else None,
        dry_run=False,
        started_at=effective_now,
    )
    automation.status = "running"
    automation.updated_at = effective_now
    db.session.add(run)
    db.session.commit()  # durable audit row before intelligence work begins

    try:
        output = build_owned_automation_output(
            owner_id=owner_id,
            automation=automation,
            event_id=event_id,
        )
        finished = datetime.utcnow() if now is None else effective_now
        run.status = "succeeded"
        run.output_json = json.dumps(output, ensure_ascii=False, sort_keys=True, default=str)
        run.error_message = None
        run.finished_at = finished
        automation.last_run_at = finished
        automation.status = "ready"
        if automation.trigger_type in {"schedule_daily", "schedule_weekly"}:
            automation.next_run_at = calculate_next_run_at(
                trigger_type=automation.trigger_type,
                trigger_config=automation.trigger_config,
                timezone_name=automation.timezone,
                now=finished,
            )
        if source == "event" and event_id is not None:
            automation.last_event_id = max(int(automation.last_event_id or 0), int(event_id))
        automation.updated_at = finished
        notification_event = _notification_event(
            owner_id=owner_id,
            automation=automation,
            run=run,
            output=output,
            now=finished,
        )
        db.session.commit()
    except Exception as error:
        db.session.rollback()
        failed_run = LifeOSAutomationRun.query.filter_by(id=run.id, user_id=owner_id).first()
        failed_automation = LifeOSAutomation.query.filter_by(id=automation.id, user_id=owner_id).first()
        failed_at = datetime.utcnow()
        if failed_run is not None:
            failed_run.status = "failed"
            failed_run.error_message = " ".join(str(error).split())[:2000]
            failed_run.finished_at = failed_at
        if failed_automation is not None:
            failed_automation.status = "error"
            failed_automation.updated_at = failed_at
        db.session.commit()
        raise

    # Delivery is separate from the execution transaction. If materialization
    # fails, the normalized automation event remains persisted and I15 can pick
    # it up on the next normal refresh without rerunning the automation.
    if notification_event is not None:
        try:
            refresh_owned_proactive_notifications(owner_id=owner_id, now=datetime.utcnow())
        except Exception:
            db.session.rollback()

    refreshed_run = LifeOSAutomationRun.query.filter_by(id=run.id, user_id=owner_id).first() or run
    return AutomationExecutionResult(
        automation_id=automation.id,
        run=refreshed_run,
        output=output,
        notification_event_id=(notification_event.id if notification_event is not None else None),
    )


def execute_owned_automation_cycle(*, owner_id: int, now: datetime | None = None) -> AutomationExecutionCycle:
    """Find and execute all currently due/matching automations for one owner."""

    cycle = collect_owned_automation_candidates(owner_id=owner_id, now=now)
    results: list[AutomationExecutionResult] = []
    failures: list[dict[str, Any]] = []
    for candidate in cycle.candidates:
        try:
            result = execute_owned_automation(
                owner_id=owner_id,
                automation_id=candidate.automation_id,
                trigger_source=candidate.trigger_source,
                event_id=candidate.event_id,
                now=cycle.scanned_at,
            )
            results.append(result)
        except Exception as error:
            failures.append({
                "automation_id": candidate.automation_id,
                "automation_name": candidate.automation_name,
                "trigger_source": candidate.trigger_source,
                "event_id": candidate.event_id,
                "error": " ".join(str(error).split())[:500],
            })
    return AutomationExecutionCycle(
        owner_id=owner_id,
        candidates=cycle.candidates,
        results=tuple(results),
        failures=tuple(failures),
        scanned_at=cycle.scanned_at,
    )

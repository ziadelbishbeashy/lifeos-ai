"""V-SPACE Smart Planner V1.

Stage 3 adds high-confidence natural-language planning on top of the deterministic
Stage 2 scheduler. User prompts may describe dates, fixed time, focus durations,
energy level, priorities and rebalance intent. Language understanding remains
read-only; exact time arithmetic stays deterministic and every generated plan
still requires I9 confirmation before it replaces an accepted schedule.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import json
from typing import Any, Iterable

from sqlalchemy.exc import SQLAlchemyError

from database import db
from services.smart_planner_language_service import (
    DEFAULT_POINT_COMMITMENT_MINUTES,
    PlannerLanguageInterpretation,
    interpret_planner_request,
)
from services.personalization_profile_service import (
    planner_defaults_for_user,
    profile_for_user,
    recurring_commitments_for_range,
)
from services.module_assessment_service import (
    assessment_target_date,
    assessment_target_kind,
    assessment_target_time,
)

from models import (
    LearningModule,
    LifeOSActionProposal,
    ModuleAssessment,
    Project,
    SmartPlannerBlock,
    SmartPlannerCommitment,
    SmartPlannerPlan,
    Task,
)


ACTION_APPLY_SMART_PLAN = "apply_smart_plan"
SMART_PLANNER_PAYLOAD_VERSION = 3
SMART_PLANNER_MODES = frozenset({"day", "week", "goal"})
COMMITMENT_TYPES = frozenset({"class", "meeting", "exam", "appointment", "personal", "other"})
IMPORTANCE_WEIGHT = {"Critical": 100, "High": 75, "Medium": 50, "Low": 25}
DIFFICULTY_MINUTES = {"Easy": 30, "Medium": 60, "Hard": 90}
MAX_CANDIDATE_TASKS = 80
MAX_BLOCKS = 80
MAX_GOAL_DAYS = 14
ACADEMIC_ASSESSMENT_MINUTES = 60
ASSESSMENT_PREP_LOOKAHEAD_DAYS = 14
ASSESSMENT_PREP_MAX_CHUNK_MINUTES = 90
LIGHT_DAY_CAPACITY_FACTOR = 0.65
MAX_FOCUS_CHUNK_MINUTES = 90
MIN_FOCUS_CHUNK_MINUTES = 30
NATURAL_BLOCK_TYPES = frozenset({"focus", "assessment_prep", "inferred_commitment"})


class SmartPlannerError(RuntimeError):
    pass


class SmartPlannerValidationError(SmartPlannerError, ValueError):
    pass


class SmartPlannerPersistenceError(SmartPlannerError):
    pass


@dataclass(frozen=True)
class PlannerConfig:
    mode: str
    start_date: date
    end_date: date
    working_start: time
    working_end: time
    break_minutes: int
    project_id: int | None
    request_text: str | None
    horizon_days: int

    @property
    def dates(self) -> tuple[date, ...]:
        if self.mode == "day":
            count = 1
        elif self.mode == "week":
            count = 7
        else:
            count = self.horizon_days
        return tuple(self.start_date + timedelta(days=index) for index in range(count))


def _parse_date(value: Any, *, default: date | None = None) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return default or date.today()
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise SmartPlannerValidationError("Choose a valid planner date.") from error


def _parse_time(value: Any, *, default: time | None = None) -> time:
    text = str(value or "").strip()
    if not text and default is not None:
        return default
    try:
        parsed = time.fromisoformat(text)
    except ValueError as error:
        raise SmartPlannerValidationError("Choose valid times.") from error
    return parsed.replace(second=0, microsecond=0)


def _parse_horizon(raw: dict[str, Any], mode: str) -> int:
    if mode == "day":
        return 1
    if mode == "week":
        return 7
    try:
        value = int(raw.get("horizon_days") or 7)
    except (TypeError, ValueError) as error:
        raise SmartPlannerValidationError("Goal horizon must be a number of days.") from error
    if value < 2 or value > MAX_GOAL_DAYS:
        raise SmartPlannerValidationError(f"Goal horizon must be between 2 and {MAX_GOAL_DAYS} days.")
    return value


def normalize_planner_config(payload: dict[str, Any] | None, *, owner_id: int) -> PlannerConfig:
    raw = payload if isinstance(payload, dict) else {}
    mode = str(raw.get("mode") or "day").strip().casefold()
    if mode not in SMART_PLANNER_MODES:
        raise SmartPlannerValidationError("Smart Planner supports Day, Week and Goal plans.")

    start_date = _parse_date(raw.get("start_date"))
    horizon_days = _parse_horizon(raw, mode)
    end_date = start_date + timedelta(days=horizon_days - 1)
    personalization_defaults = planner_defaults_for_user(int(owner_id))
    working_start = _parse_time(raw.get("working_start"), default=time.fromisoformat(personalization_defaults["working_start"]))
    working_end = _parse_time(raw.get("working_end"), default=time.fromisoformat(personalization_defaults["working_end"]))
    start_dt = datetime.combine(start_date, working_start)
    end_dt = datetime.combine(start_date, working_end)
    work_minutes = int((end_dt - start_dt).total_seconds() // 60)
    if work_minutes < 120:
        raise SmartPlannerValidationError("Give Smart Planner at least a 2-hour working window.")
    if work_minutes > 16 * 60:
        raise SmartPlannerValidationError("Working hours cannot exceed 16 hours per day.")

    try:
        raw_break = raw.get("break_minutes")
        break_minutes = int(personalization_defaults["break_minutes"] if raw_break in (None, "") else raw_break)
    except (TypeError, ValueError) as error:
        raise SmartPlannerValidationError("Break length must be a number of minutes.") from error
    if break_minutes < 0 or break_minutes > 60:
        raise SmartPlannerValidationError("Break length must be between 0 and 60 minutes.")

    raw_project = raw.get("project_id")
    project_id: int | None = None
    if raw_project not in (None, "", 0, "0"):
        try:
            project_id = int(raw_project)
        except (TypeError, ValueError) as error:
            raise SmartPlannerValidationError("Choose a valid project filter.") from error
        owned = Project.query.filter_by(id=project_id, user_id=int(owner_id)).first()
        if owned is None:
            raise SmartPlannerValidationError("That project is not available in your workspace.")

    request_text = " ".join(str(raw.get("request_text") or "").split())[:600] or None
    if mode == "goal" and not request_text:
        raise SmartPlannerValidationError("Tell V-SPACE what goal you want this plan to move forward.")
    return PlannerConfig(
        mode=mode,
        start_date=start_date,
        end_date=end_date,
        working_start=working_start,
        working_end=working_end,
        break_minutes=break_minutes,
        project_id=project_id,
        request_text=request_text,
        horizon_days=horizon_days,
    )


def _clean_text(value: Any, *, limit: int, required: bool = False) -> str | None:
    text = " ".join(str(value or "").split())[:limit]
    if required and not text:
        raise SmartPlannerValidationError("Commitment title is required.")
    return text or None


def _commitment_type(value: Any) -> str:
    result = str(value or "other").strip().casefold()
    if result not in COMMITMENT_TYPES:
        raise SmartPlannerValidationError("Choose a valid commitment type.")
    return result


def _validate_commitment_window(day: date, start_value: Any, end_value: Any) -> tuple[time, time]:
    start_at = _parse_time(start_value)
    end_at = _parse_time(end_value)
    if datetime.combine(day, end_at) <= datetime.combine(day, start_at):
        raise SmartPlannerValidationError("Commitment end time must be after its start time.")
    return start_at, end_at


def commitment_to_dict(row: SmartPlannerCommitment) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "title": row.title,
        "date": row.commitment_date.isoformat(),
        "start_time": row.start_time.strftime("%H:%M"),
        "end_time": row.end_time.strftime("%H:%M"),
        "commitment_type": row.commitment_type,
        "notes": row.notes,
        "source": "manual",
        "editable": True,
    }


def list_owned_commitments(*, owner_id: int, start_date: date, end_date: date) -> list[SmartPlannerCommitment]:
    return (
        SmartPlannerCommitment.query
        .filter(
            SmartPlannerCommitment.user_id == int(owner_id),
            SmartPlannerCommitment.commitment_date >= start_date,
            SmartPlannerCommitment.commitment_date <= end_date,
        )
        .order_by(SmartPlannerCommitment.commitment_date.asc(), SmartPlannerCommitment.start_time.asc(), SmartPlannerCommitment.id.asc())
        .all()
    )


def _require_owned_commitment(*, owner_id: int, commitment_id: int) -> SmartPlannerCommitment:
    row = SmartPlannerCommitment.query.filter_by(id=int(commitment_id), user_id=int(owner_id)).first()
    if row is None:
        raise SmartPlannerValidationError("Commitment not found.")
    return row


def create_owned_commitment(*, owner_id: int, payload: dict[str, Any] | None) -> SmartPlannerCommitment:
    raw = payload if isinstance(payload, dict) else {}
    day = _parse_date(raw.get("date"))
    start_at, end_at = _validate_commitment_window(day, raw.get("start_time"), raw.get("end_time"))
    row = SmartPlannerCommitment(
        user_id=int(owner_id),
        title=_clean_text(raw.get("title"), limit=255, required=True),
        commitment_date=day,
        start_time=start_at,
        end_time=end_at,
        commitment_type=_commitment_type(raw.get("commitment_type")),
        notes=_clean_text(raw.get("notes"), limit=2000),
    )
    try:
        db.session.add(row)
        db.session.commit()
        return row
    except SQLAlchemyError as error:
        db.session.rollback()
        raise SmartPlannerPersistenceError("V-SPACE could not save that commitment.") from error


def update_owned_commitment(*, owner_id: int, commitment_id: int, payload: dict[str, Any] | None) -> SmartPlannerCommitment:
    row = _require_owned_commitment(owner_id=owner_id, commitment_id=commitment_id)
    raw = payload if isinstance(payload, dict) else {}
    day = _parse_date(raw.get("date"), default=row.commitment_date)
    start_at, end_at = _validate_commitment_window(
        day,
        raw.get("start_time") or row.start_time.strftime("%H:%M"),
        raw.get("end_time") or row.end_time.strftime("%H:%M"),
    )
    row.title = _clean_text(raw.get("title", row.title), limit=255, required=True)
    row.commitment_date = day
    row.start_time = start_at
    row.end_time = end_at
    row.commitment_type = _commitment_type(raw.get("commitment_type", row.commitment_type))
    row.notes = _clean_text(raw.get("notes", row.notes), limit=2000)
    try:
        db.session.commit()
        return row
    except SQLAlchemyError as error:
        db.session.rollback()
        raise SmartPlannerPersistenceError("V-SPACE could not update that commitment.") from error


def delete_owned_commitment(*, owner_id: int, commitment_id: int) -> None:
    row = _require_owned_commitment(owner_id=owner_id, commitment_id=commitment_id)
    try:
        db.session.delete(row)
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise SmartPlannerPersistenceError("V-SPACE could not remove that commitment.") from error


def _academic_commitments(*, owner_id: int, start_date: date, end_date: date) -> list[dict[str, Any]]:
    rows = (
        ModuleAssessment.query
        .join(LearningModule, ModuleAssessment.module_id == LearningModule.id)
        .filter(
            LearningModule.user_id == int(owner_id),
            ModuleAssessment.assessment_date.isnot(None),
            ModuleAssessment.assessment_time.isnot(None),
            ModuleAssessment.assessment_date >= start_date,
            ModuleAssessment.assessment_date <= end_date,
            ModuleAssessment.status.notin_(["Completed", "Cancelled"]),
        )
        .order_by(ModuleAssessment.assessment_date.asc(), ModuleAssessment.assessment_time.asc(), ModuleAssessment.id.asc())
        .all()
    )
    result: list[dict[str, Any]] = []
    for assessment in rows:
        day = assessment.assessment_date
        start_at = assessment.assessment_time.replace(second=0, microsecond=0)
        end_dt = datetime.combine(day, start_at) + timedelta(minutes=ACADEMIC_ASSESSMENT_MINUTES)
        module = assessment.module
        result.append({
            "id": f"academic-{assessment.id}",
            "assessment_id": int(assessment.id),
            "title": f"{assessment.title}",
            "date": day.isoformat(),
            "start_time": start_at.strftime("%H:%M"),
            "end_time": end_dt.time().strftime("%H:%M"),
            "commitment_type": "exam" if assessment.assessment_type in {"Midterm", "Final", "Quiz"} else "class",
            "notes": f"{module.title} · {assessment.assessment_type}",
            "source": "academic",
            "editable": False,
            "module_id": int(module.id),
            "module_title": module.title,
        })
    return result


def _assessment_preparation_requests(
    *, owner_id: int, start_date: date, end_date: date
) -> list[dict[str, Any]]:
    """Return deterministic study-work requests for upcoming assessments.

    Assessment rows remain the source of truth. This function only derives
    read-only planner work from confirmed workspace data.
    """

    lookahead_end = end_date + timedelta(days=ASSESSMENT_PREP_LOOKAHEAD_DAYS)
    rows = (
        ModuleAssessment.query
        .join(LearningModule, ModuleAssessment.module_id == LearningModule.id)
        .filter(
            LearningModule.user_id == int(owner_id),
            ModuleAssessment.status.notin_(["Completed", "Cancelled"]),
            ModuleAssessment.estimated_study_minutes.isnot(None),
            ModuleAssessment.estimated_study_minutes > 0,
        )
        .order_by(ModuleAssessment.id.asc())
        .all()
    )
    completed_rows = (
        SmartPlannerBlock.query
        .join(SmartPlannerPlan, SmartPlannerBlock.plan_id == SmartPlannerPlan.id)
        .filter(
            SmartPlannerPlan.user_id == int(owner_id),
            SmartPlannerBlock.block_type == "assessment_prep",
            SmartPlannerBlock.assessment_id.isnot(None),
            SmartPlannerBlock.completed_at.isnot(None),
        )
        .all()
    )
    completed_by_assessment: dict[int, int] = {}
    for block in completed_rows:
        assessment_id = int(block.assessment_id)
        completed_by_assessment[assessment_id] = (
            completed_by_assessment.get(assessment_id, 0) + int(block.minutes or 0)
        )

    result: list[dict[str, Any]] = []
    for assessment in rows:
        target = assessment_target_date(assessment)
        if target is None or target < start_date or target > lookahead_end:
            continue
        total_minutes = max(0, min(int(assessment.estimated_study_minutes or 0), 40 * 60))
        completed_minutes = completed_by_assessment.get(int(assessment.id), 0)
        minutes = max(0, total_minutes - completed_minutes)
        if minutes <= 0:
            continue
        module = assessment.module
        target_time = assessment_target_time(assessment)
        result.append({
            "assessment_id": int(assessment.id),
            "module_id": int(module.id),
            "module_title": str(module.title),
            "title": str(assessment.title),
            "assessment_type": str(assessment.assessment_type),
            "target_date": target,
            "target_time": target_time,
            "target_kind": assessment_target_kind(assessment),
            "minutes": minutes,
            "total_minutes": total_minutes,
            "completed_minutes": completed_minutes,
            "topics": str(assessment.topics or "").strip() or None,
            "weight_percent": (
                float(assessment.weight_percent)
                if assessment.weight_percent is not None
                else None
            ),
        })
    return sorted(
        result,
        key=lambda item: (
            item["target_date"],
            -(item["weight_percent"] or 0.0),
            item["assessment_id"],
        ),
    )


def fixed_commitments(*, owner_id: int, start_date: date, end_date: date) -> list[dict[str, Any]]:
    manual = [commitment_to_dict(item) for item in list_owned_commitments(owner_id=owner_id, start_date=start_date, end_date=end_date)]
    academic = _academic_commitments(owner_id=owner_id, start_date=start_date, end_date=end_date)
    routine = recurring_commitments_for_range(owner_id=owner_id, start_date=start_date, end_date=end_date)
    return sorted(manual + academic + routine, key=lambda item: (item["date"], item["start_time"], str(item["id"])))


def _effective_deadline(task: Task) -> date | None:
    project_deadline = getattr(getattr(task, "project", None), "deadline", None)
    if task.deadline and project_deadline:
        return min(task.deadline, project_deadline)
    return task.deadline or project_deadline


def _estimate_minutes(task: Task) -> int:
    return DIFFICULTY_MINUTES.get(str(task.difficulty or "Medium"), 60)


def _request_match_bonus(task: Task, request_text: str | None) -> float:
    if not request_text:
        return 0.0
    query_tokens = {token for token in request_text.casefold().replace("-", " ").split() if len(token) >= 3}
    if not query_tokens:
        return 0.0
    project = getattr(task, "project", None)
    haystack = " ".join(
        part for part in (
            str(task.title or ""),
            str(task.description or ""),
            str(getattr(project, "title", "") or ""),
            str(task.module or ""),
            str(task.tags or ""),
        )
        if part
    ).casefold()
    matched = sum(1 for token in query_tokens if token in haystack)
    return min(40.0, matched * 10.0)


def _profile_priority_bonus(task: Task, priority_keys: set[str] | None) -> float:
    keys = set(priority_keys or set())
    if not keys:
        return 0.0
    project = getattr(task, "project", None)
    haystack = " ".join(
        part for part in (
            str(task.title or ""), str(task.description or ""), str(task.module or ""),
            str(getattr(project, "title", "") or ""), str(task.tags or ""),
        ) if part
    ).casefold()
    bonus = 0.0
    if "university" in keys and (str(task.module or "").strip() or any(word in haystack for word in ("lecture", "exam", "quiz", "assignment", "study", "calculus"))):
        bonus += 12.0
    if "projects" in keys and getattr(task, "project_id", None):
        bonus += 8.0
    keyword_groups = {
        "career": ("career", "resume", "cv", "interview", "application", "job"),
        "fitness": ("gym", "workout", "training", "run", "fitness", "cardio"),
        "business": ("business", "client", "marketing", "sales", "ecommerce", "launch"),
        "personal_time": ("personal", "family", "rest", "home"),
    }
    for key, words in keyword_groups.items():
        if key in keys and any(word in haystack for word in words):
            bonus += 8.0
    return min(bonus, 24.0)


def _task_score(task: Task, *, start_date: date, request_text: str | None = None, priority_keys: set[str] | None = None) -> tuple[float, int, int]:
    importance = IMPORTANCE_WEIGHT.get(str(task.importance or "Medium"), 50)
    deadline = _effective_deadline(task)
    if deadline is None:
        urgency = 10
        days = 9999
    else:
        days = (deadline - start_date).days
        if days < 0:
            urgency = 140
        elif days == 0:
            urgency = 120
        elif days == 1:
            urgency = 100
        elif days <= 3:
            urgency = 80
        elif days <= 7:
            urgency = 55
        else:
            urgency = 25
    blocked_penalty = -35 if str(task.status or "").casefold() == "blocked" else 0
    stored = max(0.0, min(float(task.priority_score or 0), 100.0))
    score = importance + urgency + stored * 0.35 + blocked_penalty + _request_match_bonus(task, request_text) + _profile_priority_bonus(task, priority_keys)
    return score, -days, -int(task.id)


def _rationale(task: Task, *, start_date: date) -> str:
    deadline = _effective_deadline(task)
    bits: list[str] = []
    importance = str(task.importance or "Medium")
    if importance in {"Critical", "High"}:
        bits.append(f"{importance.lower()} priority")
    if deadline:
        days = (deadline - start_date).days
        if days < 0:
            bits.append("overdue")
        elif days == 0:
            bits.append("due today")
        elif days == 1:
            bits.append("due tomorrow")
        elif days <= 7:
            bits.append(f"due in {days} days")
    if str(task.status or "").casefold() == "blocked":
        bits.append("currently blocked")
    return ", ".join(bits) if bits else "Best fit from your current open workload"


def _serialize_block(*, task: Task, day: date, start_dt: datetime, minutes: int, sort_order: int, anchor_date: date, locked: bool = False, preserved: bool = False) -> dict[str, Any]:
    end_dt = start_dt + timedelta(minutes=minutes)
    project = getattr(task, "project", None)
    deadline = _effective_deadline(task)
    return {
        "task_id": int(task.id),
        "title": str(task.title),
        "date": day.isoformat(),
        "start_time": start_dt.time().strftime("%H:%M"),
        "end_time": end_dt.time().strftime("%H:%M"),
        "minutes": minutes,
        "block_type": "task",
        "project_id": int(project.id) if project is not None else None,
        "project_title": str(project.title) if project is not None else None,
        "importance": str(task.importance or "Medium"),
        "difficulty": str(task.difficulty or "Medium"),
        "deadline": deadline.isoformat() if deadline else None,
        "status": str(task.status or "Pending"),
        "rationale": "Locked in place from your accepted plan" if preserved else _rationale(task, start_date=anchor_date),
        "locked": bool(locked),
        "preserved": bool(preserved),
        "sort_order": sort_order,
    }


def _minutes_between(day: date, start_at: time, end_at: time) -> int:
    return max(0, int((datetime.combine(day, end_at) - datetime.combine(day, start_at)).total_seconds() // 60))


def _clip_interval(day: date, start_at: time, end_at: time, window_start: time, window_end: time) -> tuple[datetime, datetime] | None:
    left = max(datetime.combine(day, start_at), datetime.combine(day, window_start))
    right = min(datetime.combine(day, end_at), datetime.combine(day, window_end))
    return (left, right) if right > left else None


def _merge_intervals(intervals: Iterable[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    ordered = sorted((start, end) for start, end in intervals if end > start)
    merged: list[tuple[datetime, datetime]] = []
    for start, end in ordered:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _free_capacity(day: date, window_start: time, window_end: time, busy: list[tuple[datetime, datetime]]) -> int:
    total = _minutes_between(day, window_start, window_end)
    occupied = sum(int((end - start).total_seconds() // 60) for start, end in _merge_intervals(busy))
    return max(total - occupied, 0)


def _find_slot(*, day: date, minutes: int, window_start: time, window_end: time, busy: list[tuple[datetime, datetime]], break_minutes: int) -> datetime | None:
    cursor = datetime.combine(day, window_start)
    limit = datetime.combine(day, window_end)
    for busy_start, busy_end in _merge_intervals(busy):
        if cursor + timedelta(minutes=minutes) <= busy_start:
            return cursor
        if cursor < busy_end:
            cursor = busy_end
    if cursor + timedelta(minutes=minutes) <= limit:
        return cursor
    return None


def _productive_period_window(period: str | None) -> tuple[time, time] | None:
    """Translate a saved productivity preference into a deterministic clock window.

    This intentionally lives in the scheduler as a defensive fallback. The
    personalization service also exposes preferred_window_start/end, but the
    scheduler must not lose the placement preference if an older/partial
    profile payload omits those derived fields.
    """
    normalized = str(period or "").strip().casefold()
    windows = {
        "morning": (time(8, 0), time(12, 0)),
        "afternoon": (time(12, 0), time(17, 0)),
        "evening": (time(17, 0), time(22, 0)),
        "late_night": (time(20, 0), time(23, 59)),
    }
    return windows.get(normalized)


def _preferred_window_for_day(*, day: date, config: PlannerConfig, start_text: str | None, end_text: str | None) -> tuple[time, time] | None:
    if not start_text or not end_text:
        return None
    try:
        preferred_start = time.fromisoformat(str(start_text))
        preferred_end = time.fromisoformat(str(end_text))
    except ValueError:
        return None
    left = max(config.working_start, preferred_start)
    right = min(config.working_end, preferred_end)
    return (left, right) if right > left else None


def _find_slot_with_preference(*, day: date, minutes: int, config: PlannerConfig, busy: list[tuple[datetime, datetime]], preferred: tuple[time, time] | None) -> tuple[datetime | None, bool]:
    if preferred is not None:
        start_dt = _find_slot(
            day=day, minutes=minutes, window_start=preferred[0], window_end=preferred[1],
            busy=busy, break_minutes=config.break_minutes,
        )
        if start_dt is not None:
            return start_dt, True
    return _find_slot(
        day=day, minutes=minutes, window_start=config.working_start, window_end=config.working_end,
        busy=busy, break_minutes=config.break_minutes,
    ), False


def _find_assessment_prep_slot(
    *,
    day: date,
    minutes: int,
    config: PlannerConfig,
    busy: list[tuple[datetime, datetime]],
    preferred: tuple[time, time] | None,
    latest_end: time | None,
) -> tuple[datetime | None, bool]:
    """Find a prep slot that never crosses the assessment/due cutoff."""

    window_end = min(config.working_end, latest_end) if latest_end else config.working_end
    if window_end <= config.working_start:
        return None, False
    clipped_preferred = preferred
    if clipped_preferred is not None:
        left = max(config.working_start, clipped_preferred[0])
        right = min(window_end, clipped_preferred[1])
        clipped_preferred = (left, right) if right > left else None
    if clipped_preferred is not None:
        start_dt = _find_slot(
            day=day,
            minutes=minutes,
            window_start=clipped_preferred[0],
            window_end=clipped_preferred[1],
            busy=busy,
            break_minutes=config.break_minutes,
        )
        if start_dt is not None:
            return start_dt, True
    return (
        _find_slot(
            day=day,
            minutes=minutes,
            window_start=config.working_start,
            window_end=window_end,
            busy=busy,
            break_minutes=config.break_minutes,
        ),
        False,
    )


def _human_time(value: str | time | None) -> str:
    if value is None:
        return ""
    parsed = value if isinstance(value, time) else time.fromisoformat(str(value))
    hour = parsed.hour % 12 or 12
    return f"{hour}:{parsed.minute:02d} {'PM' if parsed.hour >= 12 else 'AM'}"


def _known_activity_times(owner_id: int) -> dict[str, Any]:
    """Return saved routine timing hints for interpreting ambiguous point times.

    The parser may use the saved AM/PM tendency and normal duration, but the
    explicit hour in the current request always wins. This keeps the priority
    order request > profile > defaults.
    """
    profile = profile_for_user(int(owner_id))
    if profile is None:
        return {}
    result: dict[str, Any] = {}
    for rule in profile.regular_commitments():
        try:
            start_at = time.fromisoformat(str(rule.get("start_time") or ""))
            end_at = time.fromisoformat(str(rule.get("end_time") or ""))
        except ValueError:
            continue
        duration = max(5, _minutes_between(date.today(), start_at, end_at)) if end_at > start_at else DEFAULT_POINT_COMMITMENT_MINUTES
        hint = {"start_time": start_at, "duration_minutes": duration}
        title = " ".join(str(rule.get("title") or "").casefold().split())
        kind = str(rule.get("commitment_type") or "").casefold().strip()
        if title:
            result[title] = hint
        if kind:
            result[kind] = hint
            if kind == "gym":
                result["workout"] = hint
    return result


def _query_candidate_tasks(*, owner_id: int, project_id: int | None, candidate_task_ids: set[int] | None, exclude_task_ids: set[int]) -> list[Task]:
    query = Task.query.filter(Task.user_id == int(owner_id), Task.status != "Completed")
    if project_id is not None:
        query = query.filter(Task.project_id == project_id)
    if candidate_task_ids is not None:
        if not candidate_task_ids:
            return []
        query = query.filter(Task.id.in_(candidate_task_ids))
    if exclude_task_ids:
        query = query.filter(~Task.id.in_(exclude_task_ids))
    return (
        query
        .order_by(Task.deadline.is_(None), Task.deadline.asc(), Task.priority_score.desc(), Task.id.asc())
        .limit(MAX_CANDIDATE_TASKS)
        .all()
    )


def _serialize_saved_block(saved: SmartPlannerBlock, *, sort_order: int, anchor_date: date) -> dict[str, Any]:
    """Serialize an accepted locked block for a deterministic rebalance preview."""

    task = saved.task
    if task is not None:
        block = _serialize_block(
            task=task,
            day=saved.block_date,
            start_dt=datetime.combine(saved.block_date, saved.start_time),
            minutes=int(saved.minutes),
            sort_order=sort_order,
            anchor_date=anchor_date,
            locked=True,
            preserved=True,
        )
        block["block_type"] = str(saved.block_type or "task")
        return block
    return {
        "task_id": None,
        "title": str(saved.title),
        "date": saved.block_date.isoformat(),
        "start_time": saved.start_time.strftime("%H:%M"),
        "end_time": saved.end_time.strftime("%H:%M"),
        "minutes": int(saved.minutes),
        "block_type": str(saved.block_type or "focus"),
        "project_id": saved.project_id,
        "project_title": saved.project_title,
        "importance": saved.importance,
        "difficulty": None,
        "deadline": saved.deadline.isoformat() if saved.deadline else None,
        "rationale": saved.rationale,
        "locked": True,
        "preserved": True,
        "sort_order": sort_order,
    }


def _natural_block(
    *,
    title: str,
    day: date,
    start_dt: datetime,
    minutes: int,
    sort_order: int,
    block_type: str,
    rationale: str,
    locked: bool = False,
    importance: str | None = "High",
) -> dict[str, Any]:
    end_dt = start_dt + timedelta(minutes=minutes)
    return {
        "task_id": None,
        "title": str(title)[:255],
        "date": day.isoformat(),
        "start_time": start_dt.time().strftime("%H:%M"),
        "end_time": end_dt.time().strftime("%H:%M"),
        "minutes": int(minutes),
        "block_type": block_type,
        "project_id": None,
        "project_title": None,
        "importance": importance,
        "difficulty": None,
        "deadline": None,
        "rationale": rationale[:2000],
        "locked": bool(locked),
        "preserved": False,
        "sort_order": int(sort_order),
    }


def _find_project_from_request(*, owner_id: int, request_text: str | None) -> int | None:
    text = " ".join(str(request_text or "").lower().split())
    if not text:
        return None
    projects = Project.query.filter_by(user_id=int(owner_id)).order_by(Project.id.asc()).all()
    matches: list[Project] = []
    for project in projects:
        title = " ".join(str(project.title or "").lower().split())
        if not title:
            continue
        simplified = title
        simplified = simplified.replace(" v1", "").replace(" v2", "").strip()
        if title in text or (len(simplified) >= 4 and simplified in text):
            matches.append(project)
    if len(matches) == 1:
        return int(matches[0].id)
    return None


def _round_up_time(value: time, *, step_minutes: int = 15) -> time:
    total = value.hour * 60 + value.minute
    rounded = ((total + step_minutes - 1) // step_minutes) * step_minutes
    rounded = min(rounded, 23 * 60 + 59)
    return time(rounded // 60, rounded % 60)


def build_smart_plan_preview(
    *,
    owner_id: int,
    payload: dict[str, Any] | None = None,
    _dates_override: tuple[date, ...] | None = None,
    _preserved_blocks: list[SmartPlannerBlock] | None = None,
    _candidate_task_ids: set[int] | None = None,
    _exclude_task_ids: set[int] | None = None,
    _rebalanced_from_plan_id: int | None = None,
    _temporary_commitments: list[dict[str, Any]] | None = None,
    _focus_requests: list[dict[str, Any]] | None = None,
    _energy_mode: str | None = None,
    _interpretation: dict[str, Any] | None = None,
    _not_before_by_day: dict[date, time] | None = None,
) -> dict[str, Any]:
    config = normalize_planner_config(payload, owner_id=owner_id)
    dates = _dates_override or config.dates
    if not dates:
        raise SmartPlannerValidationError("There are no remaining days to plan.")
    range_start, range_end = dates[0], dates[-1]
    preserved_blocks = list(_preserved_blocks or [])
    exclude_task_ids = set(_exclude_task_ids or set())
    exclude_task_ids.update(int(block.task_id) for block in preserved_blocks if block.task_id is not None)

    personalization_defaults = planner_defaults_for_user(int(owner_id))
    profile_priority_keys = set(str(item) for item in (personalization_defaults.get("priorities") or []))
    tasks = _query_candidate_tasks(
        owner_id=owner_id,
        project_id=config.project_id,
        candidate_task_ids=_candidate_task_ids,
        exclude_task_ids=exclude_task_ids,
    )
    tasks = sorted(
        tasks,
        key=lambda task: _task_score(task, start_date=range_start, request_text=config.request_text, priority_keys=profile_priority_keys),
        reverse=True,
    )

    commitments = fixed_commitments(owner_id=owner_id, start_date=range_start, end_date=range_end)
    temporary = list(_temporary_commitments or [])[:8]
    if temporary:
        explicit_keys = {
            (str(item.get("date") or ""), " ".join(str(item.get("title") or "").casefold().split()))
            for item in temporary
            if item.get("date") and item.get("title")
        }
        commitments = [
            item for item in commitments
            if not (
                item.get("source") == "profile"
                and (str(item.get("date") or ""), " ".join(str(item.get("title") or "").casefold().split())) in explicit_keys
            )
        ]
    commitments_by_day: dict[date, list[dict[str, Any]]] = {day: [] for day in dates}
    busy_by_day: dict[date, list[tuple[datetime, datetime]]] = {day: [] for day in dates}
    for item in commitments:
        day = date.fromisoformat(item["date"])
        if day not in busy_by_day:
            continue
        commitments_by_day[day].append(item)
        clipped = _clip_interval(day, time.fromisoformat(item["start_time"]), time.fromisoformat(item["end_time"]), config.working_start, config.working_end)
        if clipped:
            busy_by_day[day].append(clipped)

    # Rebalance previews may deliberately protect elapsed time on the current day.
    for day, not_before in (_not_before_by_day or {}).items():
        if day not in busy_by_day or not_before <= config.working_start:
            continue
        clipped = _clip_interval(day, config.working_start, not_before, config.working_start, config.working_end)
        if clipped:
            busy_by_day[day].append(clipped)

    day_blocks: dict[date, list[dict[str, Any]]] = {day: [] for day in dates}
    sort_order = 0
    preserved_work_minutes = 0
    inferred_commitment_minutes = 0
    preserved_work_blocks = 0
    for saved in preserved_blocks:
        if saved.block_date not in day_blocks:
            continue
        if saved.task is not None and str(saved.task.status or "") == "Completed":
            continue
        sort_order += 1
        block = _serialize_saved_block(saved, sort_order=sort_order, anchor_date=range_start)
        day_blocks[saved.block_date].append(block)
        clipped = _clip_interval(saved.block_date, saved.start_time, saved.end_time, config.working_start, config.working_end)
        if clipped:
            busy_by_day[saved.block_date].append(clipped)
        if block["block_type"] == "inferred_commitment":
            inferred_commitment_minutes += int(saved.minutes)
        else:
            preserved_work_minutes += int(saved.minutes)
            preserved_work_blocks += 1

    # High-confidence time constraints extracted from natural language remain
    # plan-local, locked blocks. They are never copied into recurring workspace
    # commitments and only persist after the normal I9 confirmation boundary.
    for item in temporary:
        try:
            day = date.fromisoformat(str(item.get("date")))
            end_at = time.fromisoformat(str(item.get("end_time")))
            raw_start = item.get("start_time")
            start_at = time.fromisoformat(str(raw_start)) if raw_start else config.working_start
        except (TypeError, ValueError):
            continue
        if day not in busy_by_day or end_at <= start_at:
            continue
        clipped = _clip_interval(day, start_at, end_at, config.working_start, config.working_end)
        if not clipped:
            continue
        start_dt, end_dt = clipped
        minutes = int((end_dt - start_dt).total_seconds() // 60)
        if minutes <= 0:
            continue
        sort_order += 1
        block = _natural_block(
            title=str(item.get("title") or "Unavailable"),
            day=day,
            start_dt=start_dt,
            minutes=minutes,
            sort_order=sort_order,
            block_type="inferred_commitment",
            rationale="Interpreted from your planning request. Review this assumption before accepting the plan.",
            locked=True,
            importance=None,
        )
        day_blocks[day].append(block)
        busy_by_day[day].append((start_dt, end_dt))
        inferred_commitment_minutes += minutes

    daily_capacity: dict[date, int] = {
        day: _free_capacity(day, config.working_start, config.working_end, busy_by_day[day])
        for day in dates
    }
    raw_free_capacity = sum(daily_capacity.values())
    energy_mode = str(_energy_mode or personalization_defaults.get("energy_mode") or "normal").strip().casefold()
    if energy_mode not in {"light", "normal", "intense"}:
        energy_mode = "normal"
    profile_capacity_factor = float(personalization_defaults.get("capacity_factor") or 1.0)
    if _energy_mode == "light":
        capacity_factor = LIGHT_DAY_CAPACITY_FACTOR
    elif _energy_mode == "intense":
        capacity_factor = 1.0
    else:
        capacity_factor = max(0.5, min(profile_capacity_factor, 1.0))
    energy_target_minutes = raw_free_capacity
    if capacity_factor < 0.999:
        energy_target_minutes = max(30, int(raw_free_capacity * capacity_factor) // 5 * 5)
    preferred_focus_minutes = max(25, min(int(personalization_defaults.get("preferred_focus_minutes") or 60), MAX_FOCUS_CHUNK_MINUTES))
    productive_period = str(personalization_defaults.get("productive_period") or "").strip() or None
    derived_productive_window = _productive_period_window(productive_period)
    preferred_start_text = personalization_defaults.get("preferred_window_start")
    preferred_end_text = personalization_defaults.get("preferred_window_end")
    if derived_productive_window is not None:
        # Defensive scheduler-level derivation: a saved productive period must
        # influence placement even when the derived string fields are absent or
        # stale. Explicit request working hours still clip this window below.
        if not preferred_start_text:
            preferred_start_text = derived_productive_window[0].strftime("%H:%M")
        if not preferred_end_text:
            preferred_end_text = derived_productive_window[1].strftime("%H:%M")
    preferred_windows = {
        day: _preferred_window_for_day(
            day=day, config=config,
            start_text=preferred_start_text,
            end_text=preferred_end_text,
        ) for day in dates
    }

    assessment_prep_requests = _assessment_preparation_requests(
        owner_id=owner_id,
        start_date=range_start,
        end_date=range_end,
    )

    scheduled_minutes = preserved_work_minutes
    focus_scheduled_minutes = 0
    assessment_prep_scheduled_minutes = 0
    unscheduled: list[dict[str, Any]] = []

    # Explicit duration requests are honoured before general open tasks because
    # they are direct user instructions, not model guesses.
    for focus_index, item in enumerate(list(_focus_requests or [])[:8], start=1):
        title = " ".join(str(item.get("title") or "Focus block").split())[:255] or "Focus block"
        try:
            requested_minutes = max(5, min(int(item.get("minutes") or 0), 8 * 60))
        except (TypeError, ValueError):
            continue
        remaining = requested_minutes
        while remaining > 0:
            desired = min(preferred_focus_minutes, MAX_FOCUS_CHUNK_MINUTES, remaining)
            placed = False
            chunk = desired
            while chunk >= MIN_FOCUS_CHUNK_MINUTES and not placed:
                for day in dates:
                    start_dt, used_preferred_window = _find_slot_with_preference(
                        day=day, minutes=chunk, config=config, busy=busy_by_day[day],
                        preferred=preferred_windows.get(day),
                    )
                    if start_dt is None:
                        continue
                    sort_order += 1
                    block = _natural_block(
                        title=title,
                        day=day,
                        start_dt=start_dt,
                        minutes=chunk,
                        sort_order=sort_order,
                        block_type="focus",
                        rationale=(
                            "Explicit focus time requested in your natural-language plan."
                            + (f" Placed near your {productive_period.replace('_', ' ')} focus preference." if used_preferred_window and productive_period and productive_period != "varies" else "")
                        ),
                        locked=False,
                        importance="High",
                    )
                    day_blocks[day].append(block)
                    busy_by_day[day].append((start_dt, start_dt + timedelta(minutes=chunk + config.break_minutes)))
                    focus_scheduled_minutes += chunk
                    scheduled_minutes += chunk
                    remaining -= chunk
                    placed = True
                    break
                if not placed:
                    chunk -= 15
            if not placed:
                break
        if remaining > 0:
            unscheduled.append({
                "task_id": None,
                "title": title,
                "minutes": remaining,
                "project_id": None,
                "project_title": None,
                "importance": "High",
                "deadline": None,
                "reason": "The requested focus time does not fit around fixed time and the selected working window.",
                "source": "focus_request",
            })

    # Confirmed assessments become deterministic preparation work. Exact
    # assessment time stays a fixed commitment; preparation is placed before it.
    for request in assessment_prep_requests:
        remaining = int(request["minutes"])
        target_day = request["target_date"]
        target_time = request["target_time"]
        eligible_days = [day for day in dates if day <= target_day]
        # If an exam has no known clock time, do not guess that prep can happen
        # after the exam on the target day. Assignment due dates are safe to use
        # through the normal working window when no due time is supplied.
        if target_time is None and request["target_kind"] == "assessment":
            eligible_days = [day for day in eligible_days if day < target_day]
        if not eligible_days:
            unscheduled.append({
                "task_id": None,
                "assessment_id": request["assessment_id"],
                "title": f'Prepare · {request["module_title"]} · {request["title"]}',
                "minutes": remaining,
                "project_id": None,
                "project_title": None,
                "importance": "High",
                "deadline": target_day.isoformat(),
                "reason": "There is no safe planning window before this assessment.",
                "source": "assessment_prep",
            })
            continue

        rounds = 0
        while remaining > 0 and rounds < 12:
            placed_this_round = False
            for day in eligible_days:
                if remaining <= 0:
                    break
                desired = min(
                    preferred_focus_minutes,
                    ASSESSMENT_PREP_MAX_CHUNK_MINUTES,
                    remaining,
                )
                chunk = desired
                placed = False
                while chunk >= MIN_FOCUS_CHUNK_MINUTES and not placed:
                    latest_end = target_time if day == target_day else None
                    start_dt, used_preferred_window = _find_assessment_prep_slot(
                        day=day,
                        minutes=chunk,
                        config=config,
                        busy=busy_by_day[day],
                        preferred=preferred_windows.get(day),
                        latest_end=latest_end,
                    )
                    if start_dt is None:
                        chunk -= 15
                        continue
                    sort_order += 1
                    topics = request.get("topics")
                    rationale = (
                        f'Preparation for {request["module_title"]} · {request["title"]} '
                        f'before {target_day.isoformat()}.'
                    )
                    if topics:
                        rationale += f" Topics: {topics}."
                    if used_preferred_window and productive_period and productive_period != "varies":
                        rationale += f" Placed near your {productive_period.replace('_', ' ')} focus preference."
                    block = _natural_block(
                        title=f'Prepare · {request["module_title"]} · {request["title"]}',
                        day=day,
                        start_dt=start_dt,
                        minutes=chunk,
                        sort_order=sort_order,
                        block_type="assessment_prep",
                        rationale=rationale,
                        locked=False,
                        importance="High",
                    )
                    block["deadline"] = target_day.isoformat()
                    block["assessment_id"] = request["assessment_id"]
                    block["module_id"] = request["module_id"]
                    block["module_title"] = request["module_title"]
                    day_blocks[day].append(block)
                    busy_by_day[day].append(
                        (start_dt, start_dt + timedelta(minutes=chunk + config.break_minutes))
                    )
                    assessment_prep_scheduled_minutes += chunk
                    scheduled_minutes += chunk
                    remaining -= chunk
                    placed = True
                    placed_this_round = True
                # one preparation chunk per assessment/day/round spreads work
                # before filling the same day again.
            if not placed_this_round:
                break
            rounds += 1

        if remaining > 0:
            unscheduled.append({
                "task_id": None,
                "assessment_id": request["assessment_id"],
                "title": f'Prepare · {request["module_title"]} · {request["title"]}',
                "minutes": remaining,
                "project_id": None,
                "project_title": None,
                "importance": "High",
                "deadline": target_day.isoformat(),
                "reason": "Not all preparation fits before the assessment around your fixed commitments.",
                "source": "assessment_prep",
            })

    task_minutes_total = sum(_estimate_minutes(task) for task in tasks)
    total_candidate_minutes = (
        preserved_work_minutes
        + sum(max(0, int(item.get("minutes") or 0)) for item in list(_focus_requests or [])[:8])
        + sum(int(item["minutes"]) for item in assessment_prep_requests)
        + task_minutes_total
    )
    task_budget_limit = energy_target_minutes if capacity_factor < 0.999 else raw_free_capacity

    for task in tasks:
        minutes = _estimate_minutes(task)
        if capacity_factor < 0.999 and (scheduled_minutes - preserved_work_minutes) + minutes > task_budget_limit:
            project = getattr(task, "project", None)
            deadline = _effective_deadline(task)
            unscheduled.append({
                "task_id": int(task.id),
                "title": str(task.title),
                "minutes": minutes,
                "project_id": int(project.id) if project else None,
                "project_title": str(project.title) if project else None,
                "importance": str(task.importance or "Medium"),
                "deadline": deadline.isoformat() if deadline else None,
                "reason": (
                    "Light-day mode intentionally reserves recovery space instead of filling every available minute."
                    if energy_mode == "light"
                    else "Your planning-capacity preference intentionally leaves breathing room instead of filling every available minute."
                ),
                "source": "capacity_preference",
            })
            continue
        placed = False
        for day in dates:
            start_dt, used_preferred_window = _find_slot_with_preference(
                day=day, minutes=minutes, config=config, busy=busy_by_day[day],
                preferred=preferred_windows.get(day),
            )
            if start_dt is None:
                continue
            sort_order += 1
            block = _serialize_block(task=task, day=day, start_dt=start_dt, minutes=minutes, sort_order=sort_order, anchor_date=range_start)
            if used_preferred_window and productive_period and productive_period != "varies":
                existing_rationale = str(block.get("rationale") or "").rstrip(".")
                block["rationale"] = f"{existing_rationale}. Placed near your {productive_period.replace('_', ' ')} focus preference."
            day_blocks[day].append(block)
            scheduled_minutes += minutes
            busy_by_day[day].append((start_dt, start_dt + timedelta(minutes=minutes + config.break_minutes)))
            placed = True
            break
        if not placed:
            project = getattr(task, "project", None)
            deadline = _effective_deadline(task)
            unscheduled.append({
                "task_id": int(task.id),
                "title": str(task.title),
                "minutes": minutes,
                "project_id": int(project.id) if project else None,
                "project_title": str(project.title) if project else None,
                "importance": str(task.importance or "Medium"),
                "deadline": deadline.isoformat() if deadline else None,
                "reason": "No remaining free block is large enough after fixed commitments and locked work.",
                "source": "workspace_task",
            })

    deferred_minutes = sum(
        int(item["minutes"]) for item in unscheduled
        if item.get("source") == "capacity_preference"
    )
    overload_minutes = sum(int(item["minutes"]) for item in unscheduled) - deferred_minutes
    unscheduled_minutes = overload_minutes + deferred_minutes
    days_payload: list[dict[str, Any]] = []
    commitment_minutes_total = inferred_commitment_minutes
    work_block_count = 0
    for day in dates:
        blocks = sorted(day_blocks[day], key=lambda item: (item["start_time"], item["sort_order"]))
        work_blocks = [block for block in blocks if block.get("block_type") != "inferred_commitment"]
        used = sum(int(block["minutes"]) for block in work_blocks)
        work_block_count += len(work_blocks)
        commit_minutes = sum(int(block["minutes"]) for block in blocks if block.get("block_type") == "inferred_commitment")
        for item in commitments_by_day[day]:
            clipped = _clip_interval(day, time.fromisoformat(item["start_time"]), time.fromisoformat(item["end_time"]), config.working_start, config.working_end)
            if clipped:
                commit_minutes += int((clipped[1] - clipped[0]).total_seconds() // 60)
        # Inferred commitments were already counted globally above.
        commitment_minutes_total += commit_minutes - sum(int(block["minutes"]) for block in blocks if block.get("block_type") == "inferred_commitment")
        raw_window = _minutes_between(day, config.working_start, config.working_end)
        days_payload.append({
            "date": day.isoformat(),
            "label": day.strftime("%A"),
            "blocks": blocks,
            "commitments": commitments_by_day[day],
            "scheduled_minutes": used,
            "commitment_minutes": commit_minutes,
            "available_minutes": max(raw_window - commit_minutes, 0),
            "free_minutes": max(raw_window - commit_minutes - used, 0),
        })

    if not tasks and not preserved_work_blocks and not _focus_requests:
        summary = "There are no open tasks or requested focus blocks in the selected scope, so V-SPACE has nothing to schedule yet."
    elif capacity_factor < 0.999:
        summary = (
            f"V-SPACE built a realistic plan with {scheduled_minutes} minutes of focused work around "
            f"{commitment_minutes_total} minutes of fixed time. Some capacity is intentionally left open based on your planning preference."
        )
    elif overload_minutes:
        summary = (
            f"V-SPACE scheduled {scheduled_minutes} minutes around {commitment_minutes_total} minutes of fixed commitments "
            f"and left {overload_minutes} minutes unscheduled. Nothing was squeezed into an impossible window."
        )
    else:
        summary = (
            f"V-SPACE fit {work_block_count} work block{'s' if work_block_count != 1 else ''} around your fixed commitments "
            "inside the selected working window."
        )

    if config.mode == "day":
        today = date.today()
        if range_start == today:
            title = "Today plan"
        elif range_start == today + timedelta(days=1):
            title = "Tomorrow plan"
        else:
            title = f"{range_start.strftime('%a %d %b')} plan"
    elif config.mode == "week":
        title = "Week plan"
    else:
        title = f"Goal plan · {len(dates)} days"
    if config.project_id is not None:
        project = Project.query.filter_by(id=config.project_id, user_id=int(owner_id)).first()
        if project is not None:
            title = f"{title} · {project.title}"

    planned_new_work = max(scheduled_minutes - preserved_work_minutes, 0)
    energy_reserve_minutes = max(raw_free_capacity - max(energy_target_minutes, planned_new_work), 0) if capacity_factor < 0.999 else 0
    overload_preference = str(personalization_defaults.get("overload_behavior") or "leave_unscheduled")
    if overload_minutes:
        if overload_preference == "ask":
            summary += " Your profile says to ask before changing overloaded plans, so excess work is left unscheduled for your review."
        elif overload_preference == "defer_low_priority":
            summary += " Your profile prefers lower-priority work to remain for a later plan rather than crowd today."
        elif overload_preference == "shorten_optional":
            summary += " V-SPACE will not silently shorten explicit or fixed work; excess work stays unscheduled for review."

    raw_payload = payload if isinstance(payload, dict) else {}
    profile_sources = dict(personalization_defaults.get("sources") or {})
    effective_sources = dict(profile_sources)
    profile_start = str(personalization_defaults.get("working_start") or "09:00")
    profile_end = str(personalization_defaults.get("working_end") or "17:00")
    profile_break = int(personalization_defaults.get("break_minutes") or 15)
    if raw_payload.get("working_start") not in (None, "") and config.working_start.strftime("%H:%M") != profile_start:
        effective_sources["working_start"] = "request"
    if raw_payload.get("working_end") not in (None, "") and config.working_end.strftime("%H:%M") != profile_end:
        effective_sources["working_end"] = "request"
    if raw_payload.get("break_minutes") not in (None, "") and int(config.break_minutes) != profile_break:
        effective_sources["break_minutes"] = "request"
    if _energy_mode is not None:
        effective_sources["energy_mode"] = "request"

    personalization_reasons = list(personalization_defaults.get("explanations") or [])
    if profile_priority_keys:
        labels = {"university": "university", "projects": "projects", "career": "career", "fitness": "fitness", "business": "business", "personal_time": "personal life"}
        readable = ", ".join(labels.get(item, item.replace("_", " ")) for item in sorted(profile_priority_keys))
        personalization_reasons.append(f"Task ranking gives a small preference to work that matches your selected priorities: {readable}.")
    seen_profile_commitments: set[tuple[str, str, str, str]] = set()
    for day in dates:
        for item in commitments_by_day.get(day, []):
            if item.get("source") != "profile":
                continue
            key = (str(item.get("title") or ""), str(item.get("start_time") or ""), str(item.get("end_time") or ""), day.strftime("%A"))
            if key in seen_profile_commitments:
                continue
            seen_profile_commitments.add(key)
            personalization_reasons.append(
                f"{item.get('title') or 'A regular commitment'} is protected on {day.strftime('%A')} from {_human_time(item.get('start_time'))} to {_human_time(item.get('end_time'))} from your V-SPACE Profile."
            )
    # Keep explanations concise and deterministic in the preview.
    personalization_reasons = personalization_reasons[:10]

    return {
        "version": SMART_PLANNER_PAYLOAD_VERSION,
        "title": title,
        "mode": config.mode,
        "start_date": range_start.isoformat(),
        "end_date": range_end.isoformat(),
        "horizon_days": len(dates),
        "working_start": config.working_start.strftime("%H:%M"),
        "working_end": config.working_end.strftime("%H:%M"),
        "break_minutes": config.break_minutes,
        "project_id": config.project_id,
        "request_text": config.request_text,
        "summary": summary,
        "available_minutes": (energy_target_minutes + preserved_work_minutes) if capacity_factor < 0.999 else (raw_free_capacity + preserved_work_minutes),
        "scheduled_minutes": scheduled_minutes,
        "candidate_minutes": total_candidate_minutes,
        "commitment_minutes": commitment_minutes_total,
        "overload_minutes": overload_minutes,
        "deferred_minutes": deferred_minutes,
        "unscheduled_minutes": unscheduled_minutes,
        "energy_mode": energy_mode,
        "energy_reserve_minutes": energy_reserve_minutes,
        "scheduled_tasks": work_block_count,
        "candidate_tasks": len(tasks) + len(list(_focus_requests or [])[:8]) + len(assessment_prep_requests) + preserved_work_blocks,
        "assessment_prep_minutes": assessment_prep_scheduled_minutes,
        "days": days_payload,
        "unscheduled": unscheduled,
        "rebalanced_from_plan_id": _rebalanced_from_plan_id,
        "interpretation": _interpretation,
        "read_only": True,
        "verified_from_state": True,
        "confirmation_required": True,
        "planning_defaults": {
            "working_start": config.working_start.strftime("%H:%M"),
            "working_end": config.working_end.strftime("%H:%M"),
            "break_minutes": config.break_minutes,
            "energy_mode": energy_mode,
            "capacity_factor": capacity_factor,
            "preferred_focus_minutes": preferred_focus_minutes,
            "productive_period": productive_period,
            "sources": effective_sources,
            "profile_applied": any(value == "profile" for value in effective_sources.values()) or bool(personalization_reasons),
            "overload_preference": overload_preference,
            "reasons": personalization_reasons,
        },
    }


def build_natural_language_plan_preview(*, owner_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = dict(payload or {})
    request_text = " ".join(str(raw.get("request_text") or "").split())[:1200]
    if not request_text:
        raise SmartPlannerValidationError("Tell V-SPACE what you want to plan.")
    interpretation: PlannerLanguageInterpretation = interpret_planner_request(
        request_text, anchor_date=date.today(), known_activity_times=_known_activity_times(owner_id)
    )
    if interpretation.clarifications:
        raise SmartPlannerValidationError(
            "I need one detail before I can build this plan: " + " ".join(interpretation.clarifications)
        )
    structured = dict(raw)
    if interpretation.mode:
        structured["mode"] = interpretation.mode
    if interpretation.start_date:
        structured["start_date"] = interpretation.start_date.isoformat()
    if interpretation.horizon_days and structured.get("mode") == "goal":
        structured["horizon_days"] = interpretation.horizon_days
    if not structured.get("project_id"):
        inferred_project = _find_project_from_request(owner_id=owner_id, request_text=request_text)
        if inferred_project is not None:
            structured["project_id"] = inferred_project
    structured["request_text"] = request_text

    if interpretation.rebalance_requested:
        target = interpretation.start_date or date.today()
        active = latest_owned_smart_plan(owner_id=owner_id, target_date=target)
        if active is not None:
            not_before = _round_up_time(datetime.now().time()) if interpretation.from_now and target == date.today() else None
            preview = build_rebalance_preview(
                owner_id=owner_id,
                plan_id=active.id,
                from_date=target,
                from_time=not_before,
                request_text=request_text,
                interpretation=interpretation.to_dict(),
            )
            preview["interpretation"] = interpretation.to_dict()
            return preview

    return build_smart_plan_preview(
        owner_id=owner_id,
        payload=structured,
        _temporary_commitments=[item.to_dict() for item in interpretation.commitments],
        _focus_requests=[item.to_dict() for item in interpretation.focus_requests],
        _energy_mode=interpretation.energy_mode if interpretation.energy_mode != "normal" else None,
        _interpretation=interpretation.to_dict(),
    )


def prepare_natural_language_plan_proposal(*, owner_id: int, payload: dict[str, Any] | None = None) -> LifeOSActionProposal:
    return _proposal_from_preview(owner_id=owner_id, preview=build_natural_language_plan_preview(owner_id=owner_id, payload=payload))

def _plan_evidence(preview: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for day in preview.get("days", []):
        for block in day.get("blocks", []):
            task_id = block.get("task_id")
            if not isinstance(task_id, int) or task_id in seen:
                continue
            seen.add(task_id)
            result.append({
                "source_type": "task",
                "source_id": task_id,
                "label": str(block.get("title") or "Task")[:255],
                "field": "planner_candidate",
                "freshness": "current",
            })
            if len(result) >= 12:
                return result
    return result


def _proposal_from_preview(*, owner_id: int, preview: dict[str, Any]) -> LifeOSActionProposal:
    if int(preview.get("scheduled_tasks") or 0) <= 0:
        raise SmartPlannerValidationError("There are no schedulable open tasks in this planner scope.")
    proposal_payload = {"version": SMART_PLANNER_PAYLOAD_VERSION, "preview": preview}
    payload_json = json.dumps(proposal_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    evidence_json = json.dumps(_plan_evidence(preview), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    existing = (
        LifeOSActionProposal.query
        .filter_by(user_id=int(owner_id), action_type=ACTION_APPLY_SMART_PLAN, status="pending")
        .order_by(LifeOSActionProposal.created_at.desc())
        .limit(12)
        .all()
    )
    for proposal in existing:
        if proposal.payload_json == payload_json:
            return proposal
    proposal = LifeOSActionProposal(
        user_id=int(owner_id),
        action_type=ACTION_APPLY_SMART_PLAN,
        status="pending",
        title=f"Accept Smart Planner: {preview['title']}"[:255],
        reason=preview["summary"],
        target_type="smart_planner_plan",
        target_id=preview.get("rebalanced_from_plan_id"),
        project_id=preview.get("project_id"),
        payload_json=payload_json,
        evidence_json=evidence_json,
        risk_level="medium",
        requires_confirmation=True,
    )
    try:
        db.session.add(proposal)
        db.session.commit()
        return proposal
    except SQLAlchemyError as error:
        db.session.rollback()
        raise SmartPlannerPersistenceError("V-SPACE could not prepare this plan for confirmation.") from error


def prepare_smart_plan_proposal(*, owner_id: int, payload: dict[str, Any] | None = None) -> LifeOSActionProposal:
    return _proposal_from_preview(owner_id=owner_id, preview=build_smart_plan_preview(owner_id=owner_id, payload=payload))


def _require_owned_plan(*, owner_id: int, plan_id: int) -> SmartPlannerPlan:
    plan = SmartPlannerPlan.query.filter_by(id=int(plan_id), user_id=int(owner_id)).first()
    if plan is None:
        raise SmartPlannerValidationError("Smart Planner plan not found.")
    return plan


def build_rebalance_preview(
    *,
    owner_id: int,
    plan_id: int,
    from_date: date | None = None,
    from_time: time | None = None,
    request_text: str | None = None,
    interpretation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = _require_owned_plan(owner_id=owner_id, plan_id=plan_id)
    if plan.status != "accepted":
        raise SmartPlannerValidationError("Only the current accepted schedule can be rebalanced.")
    start = max(from_date or date.today(), plan.start_date)
    if start > plan.end_date:
        raise SmartPlannerValidationError("This plan has no remaining days to rebalance.")
    dates = tuple(start + timedelta(days=index) for index in range((plan.end_date - start).days + 1))
    locked: list[SmartPlannerBlock] = []
    focus_totals: dict[str, int] = {}
    for block in plan.blocks:
        if block.block_date < start:
            continue
        if block.completed_at is not None:
            continue
        if block.task is not None and str(block.task.status or "") == "Completed":
            continue
        if block.locked:
            locked.append(block)
            continue
        if str(block.block_type or "") == "focus":
            focus_totals[str(block.title)] = focus_totals.get(str(block.title), 0) + int(block.minutes)

    payload = {
        "mode": plan.mode if plan.mode in SMART_PLANNER_MODES else ("day" if len(dates) == 1 else "week"),
        "start_date": start.isoformat(),
        "horizon_days": len(dates),
        "working_start": plan.working_start.strftime("%H:%M"),
        "working_end": plan.working_end.strftime("%H:%M"),
        "break_minutes": int(plan.break_minutes),
        "project_id": plan.project_id,
        "request_text": request_text or plan.request_text or "Rebalance the remaining accepted plan",
    }
    if payload["mode"] == "goal":
        payload["horizon_days"] = max(2, min(MAX_GOAL_DAYS, len(dates)))
    not_before: dict[date, time] = {}
    if from_time is not None and start == date.today():
        not_before[start] = from_time
    return build_smart_plan_preview(
        owner_id=owner_id,
        payload=payload,
        _dates_override=dates,
        _preserved_blocks=locked,
        _focus_requests=[{"title": title, "minutes": minutes, "source_text": "accepted plan"} for title, minutes in focus_totals.items()],
        _rebalanced_from_plan_id=int(plan.id),
        _interpretation=interpretation,
        _not_before_by_day=not_before,
    )

def prepare_rebalance_proposal(*, owner_id: int, plan_id: int, from_date: date | None = None) -> LifeOSActionProposal:
    return _proposal_from_preview(owner_id=owner_id, preview=build_rebalance_preview(owner_id=owner_id, plan_id=plan_id, from_date=from_date))


def _payload_time(value: Any) -> time:
    try:
        return time.fromisoformat(str(value))
    except ValueError as error:
        raise SmartPlannerValidationError("The saved planner proposal contains invalid times.") from error


def apply_confirmed_smart_plan(*, owner_id: int, proposal: LifeOSActionProposal) -> SmartPlannerPlan:
    payload = proposal.payload
    if payload.get("version") != SMART_PLANNER_PAYLOAD_VERSION or not isinstance(payload.get("preview"), dict):
        raise SmartPlannerValidationError("This Smart Planner proposal is out of date. Regenerate the plan before accepting it.")
    preview = payload["preview"]
    try:
        start_date = date.fromisoformat(str(preview.get("start_date")))
        end_date = date.fromisoformat(str(preview.get("end_date")))
    except ValueError as error:
        raise SmartPlannerValidationError("The Smart Planner date range is invalid.") from error
    mode = str(preview.get("mode") or "")
    if mode not in SMART_PLANNER_MODES:
        raise SmartPlannerValidationError("The Smart Planner mode is invalid.")

    blocks: list[dict[str, Any]] = []
    for day in preview.get("days", []):
        if not isinstance(day, dict):
            continue
        for block in day.get("blocks", []):
            if isinstance(block, dict):
                blocks.append(block)
    if not blocks or len(blocks) > MAX_BLOCKS:
        raise SmartPlannerValidationError("This Smart Planner proposal has no valid schedule blocks.")

    owned_tasks: dict[int, Task] = {}
    owned_assessments: dict[int, ModuleAssessment] = {}
    for block in blocks:
        block_type = str(block.get("block_type") or "task")
        raw_task_id = block.get("task_id")
        if block_type == "task":
            try:
                task_id = int(raw_task_id)
            except (TypeError, ValueError) as error:
                raise SmartPlannerValidationError("A planned task is no longer valid.") from error
            task = Task.query.filter_by(id=task_id, user_id=int(owner_id)).first()
            if task is None or str(task.status or "") == "Completed":
                raise SmartPlannerValidationError("One of the planned tasks changed or is no longer available. Regenerate the plan.")
            owned_tasks[task_id] = task
        elif block_type in NATURAL_BLOCK_TYPES:
            if raw_task_id not in (None, "", 0, "0"):
                raise SmartPlannerValidationError("A natural-language planner block contains an unexpected task reference.")
            if not " ".join(str(block.get("title") or "").split()):
                raise SmartPlannerValidationError("A natural-language planner block is missing its title.")
            if block_type == "assessment_prep":
                try:
                    assessment_id = int(block.get("assessment_id"))
                except (TypeError, ValueError) as error:
                    raise SmartPlannerValidationError("Assessment preparation is missing its assessment reference.") from error
                assessment = (
                    ModuleAssessment.query
                    .join(LearningModule, ModuleAssessment.module_id == LearningModule.id)
                    .filter(
                        ModuleAssessment.id == assessment_id,
                        LearningModule.user_id == int(owner_id),
                    )
                    .first()
                )
                if assessment is None:
                    raise SmartPlannerValidationError("An assessment preparation block is no longer available.")
                owned_assessments[assessment_id] = assessment
        else:
            raise SmartPlannerValidationError("A planner block type is no longer supported. Regenerate the plan.")

    project_id = preview.get("project_id")
    if project_id is not None:
        try:
            project_id = int(project_id)
        except (TypeError, ValueError) as error:
            raise SmartPlannerValidationError("The planner project scope is invalid.") from error
        if Project.query.filter_by(id=project_id, user_id=int(owner_id)).first() is None:
            raise SmartPlannerValidationError("The planner project scope is no longer available.")
    supersedes_plan_id = preview.get("rebalanced_from_plan_id")
    try:
        supersedes_plan_id = int(supersedes_plan_id) if supersedes_plan_id is not None else None
    except (TypeError, ValueError) as error:
        raise SmartPlannerValidationError("The rebalance source plan is invalid.") from error
    if supersedes_plan_id is not None:
        _require_owned_plan(owner_id=owner_id, plan_id=supersedes_plan_id)

    try:
        overlapping = SmartPlannerPlan.query.filter(
            SmartPlannerPlan.user_id == int(owner_id),
            SmartPlannerPlan.status == "accepted",
            SmartPlannerPlan.start_date <= end_date,
            SmartPlannerPlan.end_date >= start_date,
        ).all()
        for previous in overlapping:
            previous.status = "superseded"

        plan = SmartPlannerPlan(
            user_id=int(owner_id),
            title=str(preview.get("title") or "Smart plan")[:255],
            mode=mode,
            start_date=start_date,
            end_date=end_date,
            project_id=project_id,
            supersedes_plan_id=supersedes_plan_id,
            status="accepted",
            request_text=str(preview.get("request_text") or "")[:600] or None,
            summary=str(preview.get("summary") or "")[:4000] or None,
            working_start=_payload_time(preview.get("working_start")),
            working_end=_payload_time(preview.get("working_end")),
            break_minutes=int(preview.get("break_minutes") or 0),
            available_minutes=int(preview.get("available_minutes") or 0),
            scheduled_minutes=int(preview.get("scheduled_minutes") or 0),
            overload_minutes=int(preview.get("overload_minutes") or 0),
        )
        db.session.add(plan)
        db.session.flush()

        for index, block in enumerate(blocks, start=1):
            block_type = str(block.get("block_type") or "task")
            block_date = date.fromisoformat(str(block.get("date")))
            if block_date < start_date or block_date > end_date:
                raise SmartPlannerValidationError("A planned block falls outside the confirmed plan range.")
            start_at = _payload_time(block.get("start_time"))
            end_at = _payload_time(block.get("end_time"))
            if end_at <= start_at:
                raise SmartPlannerValidationError("A planned block contains an invalid time range.")
            minutes = max(5, min(int(block.get("minutes") or 0), 16 * 60))

            if block_type == "task":
                task_id = int(block["task_id"])
                task = owned_tasks[task_id]
                db.session.add(SmartPlannerBlock(
                    plan_id=plan.id,
                    task_id=task.id,
                    block_date=block_date,
                    start_time=start_at,
                    end_time=end_at,
                    minutes=minutes,
                    title=str(task.title)[:255],
                    block_type="task",
                    project_id=task.project_id,
                    project_title=str(getattr(getattr(task, "project", None), "title", ""))[:255] or None,
                    importance=str(task.importance or "Medium")[:24],
                    deadline=_effective_deadline(task),
                    rationale=str(block.get("rationale") or "")[:2000] or None,
                    locked=bool(block.get("locked")),
                    sort_order=index,
                ))
                continue

            deadline = None
            if block.get("deadline"):
                try:
                    deadline = date.fromisoformat(str(block.get("deadline")))
                except ValueError:
                    deadline = None
            assessment_id = None
            if block_type == "assessment_prep":
                assessment_id = int(block.get("assessment_id"))
                if assessment_id not in owned_assessments:
                    raise SmartPlannerValidationError("An assessment preparation block is no longer available.")
            db.session.add(SmartPlannerBlock(
                plan_id=plan.id,
                task_id=None,
                assessment_id=assessment_id,
                block_date=block_date,
                start_time=start_at,
                end_time=end_at,
                minutes=minutes,
                title=str(block.get("title") or ("Focus block" if block_type == "focus" else "Unavailable"))[:255],
                block_type=block_type,
                project_id=block.get("project_id"),
                project_title=str(block.get("project_title") or "")[:255] or None,
                importance=str(block.get("importance") or "")[:24] or None,
                deadline=deadline,
                rationale=str(block.get("rationale") or "")[:2000] or None,
                locked=True if block_type == "inferred_commitment" else bool(block.get("locked")),
                sort_order=index,
            ))
        db.session.commit()
        return plan
    except SmartPlannerValidationError:
        db.session.rollback()
        raise
    except (SQLAlchemyError, TypeError, ValueError) as error:
        db.session.rollback()
        raise SmartPlannerPersistenceError("V-SPACE could not save the confirmed Smart Planner schedule.") from error

def _block_state(block: SmartPlannerBlock) -> str:
    if block.completed_at is not None:
        return "completed"
    task = block.task
    if task is not None and str(task.status or "") == "Completed":
        return "completed"
    now = datetime.now()
    start_dt = datetime.combine(block.block_date, block.start_time)
    end_dt = datetime.combine(block.block_date, block.end_time)
    if now > end_dt:
        return "completed" if str(block.block_type or "") == "inferred_commitment" else "missed"
    if start_dt <= now <= end_dt:
        return "current"
    return "upcoming"


def _block_to_dict(block: SmartPlannerBlock) -> dict[str, Any]:
    return {
        "id": int(block.id),
        "task_id": int(block.task_id) if block.task_id is not None else None,
        "assessment_id": int(block.assessment_id) if block.assessment_id is not None else None,
        "completed_at": block.completed_at.isoformat() if block.completed_at else None,
        "title": block.title,
        "date": block.block_date.isoformat(),
        "start_time": block.start_time.strftime("%H:%M"),
        "end_time": block.end_time.strftime("%H:%M"),
        "minutes": int(block.minutes),
        "block_type": block.block_type,
        "project_id": block.project_id,
        "project_title": block.project_title,
        "importance": block.importance,
        "deadline": block.deadline.isoformat() if block.deadline else None,
        "rationale": block.rationale,
        "locked": bool(block.locked),
        "sort_order": int(block.sort_order),
        "task_status": str(block.task.status) if block.task is not None else None,
        "state": _block_state(block),
    }


def smart_plan_to_dict(plan: SmartPlannerPlan | None) -> dict[str, Any] | None:
    if plan is None:
        return None
    blocks_by_date: dict[str, list[dict[str, Any]]] = {}
    for block in plan.blocks:
        key = block.block_date.isoformat()
        blocks_by_date.setdefault(key, []).append(_block_to_dict(block))
    commitments = fixed_commitments(owner_id=plan.user_id, start_date=plan.start_date, end_date=plan.end_date)
    commitments_by_date: dict[str, list[dict[str, Any]]] = {}
    for item in commitments:
        commitments_by_date.setdefault(item["date"], []).append(item)
    days = []
    cursor = plan.start_date
    while cursor <= plan.end_date:
        key = cursor.isoformat()
        day_blocks = sorted(blocks_by_date.get(key, []), key=lambda item: (item["start_time"], item["sort_order"]))
        inferred_minutes = sum(int(item["minutes"]) for item in day_blocks if item.get("block_type") == "inferred_commitment")
        work_minutes = sum(int(item["minutes"]) for item in day_blocks if item.get("block_type") != "inferred_commitment")
        fixed_items = commitments_by_date.get(key, [])
        fixed_minutes = sum(
            _minutes_between(cursor, time.fromisoformat(item["start_time"]), time.fromisoformat(item["end_time"]))
            for item in fixed_items
        )
        days.append({
            "date": key,
            "label": cursor.strftime("%A"),
            "blocks": day_blocks,
            "commitments": fixed_items,
            "scheduled_minutes": work_minutes,
            "commitment_minutes": fixed_minutes + inferred_minutes,
        })
        cursor += timedelta(days=1)
    return {
        "id": int(plan.id),
        "title": plan.title,
        "mode": plan.mode,
        "start_date": plan.start_date.isoformat(),
        "end_date": plan.end_date.isoformat(),
        "project_id": plan.project_id,
        "supersedes_plan_id": plan.supersedes_plan_id,
        "status": plan.status,
        "request_text": plan.request_text,
        "summary": plan.summary,
        "working_start": plan.working_start.strftime("%H:%M"),
        "working_end": plan.working_end.strftime("%H:%M"),
        "break_minutes": int(plan.break_minutes),
        "available_minutes": int(plan.available_minutes),
        "scheduled_minutes": int(plan.scheduled_minutes),
        "commitment_minutes": sum(
            _minutes_between(date.fromisoformat(item["date"]), time.fromisoformat(item["start_time"]), time.fromisoformat(item["end_time"]))
            for item in commitments
        ) + sum(int(block.minutes) for block in plan.blocks if str(block.block_type or "") == "inferred_commitment"),
        "overload_minutes": int(plan.overload_minutes),
        "days": days,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "accepted_at": plan.accepted_at.isoformat() if plan.accepted_at else None,
    }


def _intervals_overlap(start_a: time, end_a: time, start_b: time, end_b: time) -> bool:
    return start_a < end_b and start_b < end_a


def update_owned_plan_block(*, owner_id: int, plan_id: int, block_id: int, payload: dict[str, Any] | None) -> SmartPlannerPlan:
    plan = _require_owned_plan(owner_id=owner_id, plan_id=plan_id)
    if plan.status != "accepted":
        raise SmartPlannerValidationError("Only the current accepted plan can be edited.")
    block = SmartPlannerBlock.query.filter_by(id=int(block_id), plan_id=plan.id).first()
    if block is None:
        raise SmartPlannerValidationError("Planner block not found.")
    if block.task is not None and str(block.task.status or "") == "Completed":
        raise SmartPlannerValidationError("Completed task blocks stay in place as history.")
    raw = payload if isinstance(payload, dict) else {}
    if "completed" in raw:
        if str(block.block_type or "") != "assessment_prep":
            raise SmartPlannerValidationError("Only assessment preparation blocks can be completed from the planner.")
        block.completed_at = datetime.utcnow() if bool(raw.get("completed")) else None

    day = _parse_date(raw.get("date"), default=block.block_date)
    if day < plan.start_date or day > plan.end_date:
        raise SmartPlannerValidationError("Move the block to a day inside this accepted plan.")
    start_at, end_at = _validate_commitment_window(
        day,
        raw.get("start_time") or block.start_time.strftime("%H:%M"),
        raw.get("end_time") or block.end_time.strftime("%H:%M"),
    )
    if start_at < plan.working_start or end_at > plan.working_end:
        raise SmartPlannerValidationError("Keep task blocks inside the plan's working hours.")

    for other in plan.blocks:
        if other.id == block.id or other.block_date != day:
            continue
        if _intervals_overlap(start_at, end_at, other.start_time, other.end_time):
            raise SmartPlannerValidationError(f'That time overlaps “{other.title}”.')
    for item in fixed_commitments(owner_id=owner_id, start_date=day, end_date=day):
        if _intervals_overlap(start_at, end_at, time.fromisoformat(item["start_time"]), time.fromisoformat(item["end_time"])):
            raise SmartPlannerValidationError(f'That time overlaps the fixed commitment “{item["title"]}”.')

    block.block_date = day
    block.start_time = start_at
    block.end_time = end_at
    block.minutes = _minutes_between(day, start_at, end_at)
    if "locked" in raw:
        block.locked = bool(raw.get("locked"))
    try:
        ordered = sorted(plan.blocks, key=lambda item: (item.block_date, item.start_time, item.id))
        for index, item in enumerate(ordered, start=1):
            item.sort_order = index
        plan.scheduled_minutes = sum(int(item.minutes) for item in plan.blocks if str(item.block_type or "") != "inferred_commitment")
        db.session.commit()
        return plan
    except SQLAlchemyError as error:
        db.session.rollback()
        raise SmartPlannerPersistenceError("V-SPACE could not update that planner block.") from error


def latest_owned_smart_plan(*, owner_id: int, target_date: date | None = None) -> SmartPlannerPlan | None:
    query = SmartPlannerPlan.query.filter_by(user_id=int(owner_id), status="accepted")
    if target_date is not None:
        query = query.filter(SmartPlannerPlan.start_date <= target_date, SmartPlannerPlan.end_date >= target_date)
    return query.order_by(SmartPlannerPlan.accepted_at.desc(), SmartPlannerPlan.id.desc()).first()


def planner_state(*, owner_id: int, target_date: date | None = None) -> dict[str, Any]:
    projects = Project.query.filter_by(user_id=int(owner_id)).order_by(Project.title.asc()).all()
    open_count = Task.query.filter(Task.user_id == int(owner_id), Task.status != "Completed").count()
    anchor = target_date or date.today()
    visible_commitments = fixed_commitments(owner_id=owner_id, start_date=anchor, end_date=anchor + timedelta(days=13))
    personalization_defaults = planner_defaults_for_user(int(owner_id))
    return {
        "today": date.today().isoformat(),
        "open_task_count": int(open_count),
        "projects": [{"id": int(project.id), "title": project.title} for project in projects],
        "active_plan": smart_plan_to_dict(latest_owned_smart_plan(owner_id=owner_id, target_date=target_date)),
        "commitments": visible_commitments,
        "defaults": {
            "mode": "day",
            "working_start": personalization_defaults["working_start"],
            "working_end": personalization_defaults["working_end"],
            "break_minutes": personalization_defaults["break_minutes"],
            "horizon_days": 7,
            "preferred_focus_minutes": personalization_defaults["preferred_focus_minutes"],
            "energy_mode": personalization_defaults["energy_mode"],
            "productive_period": personalization_defaults.get("productive_period"),
            "capacity_factor": personalization_defaults.get("capacity_factor", 1.0),
            "explanations": personalization_defaults.get("explanations", []),
            "sources": personalization_defaults["sources"],
        },
        "verified_from_state": True,
    }

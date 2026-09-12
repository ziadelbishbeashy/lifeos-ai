"""Privacy-first V-SPACE life-context personalization.

The profile stores optional user preferences that help deterministic product
features make better defaults. It is never treated as factual workspace state
and is not automatically attached to model/web requests.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
import json
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import User, UserPersonalizationProfile

NOTICE_VERSION = "v1"
TOTAL_QUESTIONS = 7

PRODUCTIVE_PERIODS = {"morning", "afternoon", "evening", "late_night", "varies"}
PLANNING_INTENSITIES = {"light", "balanced", "productive", "intense"}
OVERLOAD_BEHAVIORS = {"defer_low_priority", "shorten_optional", "ask", "leave_unscheduled"}
PRIORITY_KEYS = {"university", "projects", "career", "fitness", "business", "personal_time", "other"}
COMMITMENT_TYPES = {"university", "work", "gym", "training", "family", "class", "meeting", "personal", "other"}
VALID_FOCUS_MINUTES = {25, 45, 60, 90}
VALID_BREAK_MINUTES = {5, 10, 15, 20}
MAX_COMMITMENTS = 12

FIELD_USAGE: dict[str, list[str]] = {
    "usual_wake_time": ["Smart Planner"],
    "usual_sleep_time": ["Smart Planner"],
    "productive_period": ["Smart Planner", "Focus Studio"],
    "preferred_focus_minutes": ["Smart Planner", "Focus Studio"],
    "preferred_break_minutes": ["Smart Planner", "Focus Studio"],
    "planning_intensity": ["Smart Planner"],
    "workday_start": ["Smart Planner"],
    "workday_end": ["Smart Planner"],
    "avoid_after_time": ["Smart Planner"],
    "regular_commitments": ["Smart Planner"],
    "priorities": ["Smart Planner", "Dashboard", "Ask V-SPACE"],
    "overload_behavior": ["Smart Planner"],
}


class PersonalizationValidationError(ValueError):
    pass


class PersonalizationPersistenceError(RuntimeError):
    pass


def _parse_optional_time(value: Any, *, field_label: str) -> time | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = time.fromisoformat(text)
    except ValueError as error:
        raise PersonalizationValidationError(f"Choose a valid {field_label} time.") from error
    return parsed.replace(second=0, microsecond=0)


def _serialize_time(value: time | None) -> str | None:
    return value.strftime("%H:%M") if value else None


def _choice(value: Any, allowed: set[str], *, field_label: str, allow_empty: bool = True) -> str | None:
    normalized = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    if not normalized and allow_empty:
        return None
    if normalized not in allowed:
        raise PersonalizationValidationError(f"Choose a supported {field_label} option.")
    return normalized


def _int_choice(value: Any, allowed: set[int], *, field_label: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise PersonalizationValidationError(f"Choose a supported {field_label} option.") from error
    if parsed not in allowed:
        raise PersonalizationValidationError(f"Choose a supported {field_label} option.")
    return parsed


def _normalize_priorities(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, (list, tuple, set)):
        raise PersonalizationValidationError("Priorities must be a list.")
    result: list[str] = []
    for raw in value:
        item = _choice(raw, PRIORITY_KEYS, field_label="priority", allow_empty=False)
        assert item is not None
        if item not in result:
            result.append(item)
    return result[:6]


def _normalize_days(value: Any) -> list[int]:
    if not isinstance(value, (list, tuple, set)) or not value:
        raise PersonalizationValidationError("Choose at least one day for each regular commitment.")
    days: list[int] = []
    for raw in value:
        try:
            day = int(raw)
        except (TypeError, ValueError) as error:
            raise PersonalizationValidationError("Commitment days must be valid weekdays.") from error
        if day < 0 or day > 6:
            raise PersonalizationValidationError("Commitment days must be valid weekdays.")
        if day not in days:
            days.append(day)
    return sorted(days)


def _normalize_commitments(value: Any) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise PersonalizationValidationError("Regular commitments must be a list.")
    if len(value) > MAX_COMMITMENTS:
        raise PersonalizationValidationError(f"Add at most {MAX_COMMITMENTS} regular commitments.")
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise PersonalizationValidationError("Each regular commitment must be structured.")
        title = " ".join(str(raw.get("title") or "").split())[:80]
        if not title:
            raise PersonalizationValidationError("Each regular commitment needs a title.")
        start_at = _parse_optional_time(raw.get("start_time"), field_label="commitment start")
        end_at = _parse_optional_time(raw.get("end_time"), field_label="commitment end")
        if start_at is None or end_at is None or end_at <= start_at:
            raise PersonalizationValidationError("Each regular commitment needs a valid start and end time.")
        commitment_type = _choice(raw.get("commitment_type") or "other", COMMITMENT_TYPES, field_label="commitment type", allow_empty=False)
        result.append({
            "key": f"routine-{index + 1}",
            "title": title,
            "days": _normalize_days(raw.get("days")),
            "start_time": start_at.strftime("%H:%M"),
            "end_time": end_at.strftime("%H:%M"),
            "commitment_type": commitment_type,
        })
    return result


def profile_for_user(user_or_id: User | int) -> UserPersonalizationProfile | None:
    if hasattr(user_or_id, "id"):
        return getattr(user_or_id, "personalization_profile", None)
    return UserPersonalizationProfile.query.filter_by(user_id=int(user_or_id)).first()


def get_or_create_profile(user: User) -> UserPersonalizationProfile:
    profile = user.personalization_profile
    if profile is None:
        profile = UserPersonalizationProfile(user_id=int(user.id), onboarding_state="deferred")
        db.session.add(profile)
        db.session.flush()
    return profile


def _answered_count(profile: UserPersonalizationProfile | None) -> int:
    """Count the seven user-facing personalization steps, not raw DB fields.

    V2 deliberately presents personalization as seven understandable decisions.
    Several steps store more than one field (for example wake + sleep), so a raw
    field count would produce confusing values such as "10 / 7" in Settings.
    """
    if profile is None:
        return 0
    groups = [
        bool(profile.priorities()),
        bool(profile.usual_wake_time or profile.usual_sleep_time),
        bool(profile.regular_commitments()),
        bool(profile.productive_period),
        bool(profile.preferred_focus_minutes or profile.preferred_break_minutes),
        bool(profile.planning_intensity),
        bool(profile.overload_behavior or profile.workday_start or profile.workday_end or profile.avoid_after_time),
    ]
    return sum(1 for configured in groups if configured)


def serialize_summary(profile: UserPersonalizationProfile | None) -> dict[str, Any]:
    state = str(profile.onboarding_state or "deferred") if profile else "not_started"
    return {
        "onboarding_state": state,
        "completed": state == "completed",
        "deferred": state == "deferred",
        "configured": bool(profile and _answered_count(profile) > 0),
        "answered_count": _answered_count(profile),
        "total_questions": TOTAL_QUESTIONS,
        "notice_version": NOTICE_VERSION,
    }


def serialize_profile(profile: UserPersonalizationProfile | None) -> dict[str, Any]:
    base = serialize_summary(profile)
    base.update({
        "usual_wake_time": _serialize_time(profile.usual_wake_time) if profile else None,
        "usual_sleep_time": _serialize_time(profile.usual_sleep_time) if profile else None,
        "productive_period": profile.productive_period if profile else None,
        "preferred_focus_minutes": profile.preferred_focus_minutes if profile else None,
        "preferred_break_minutes": profile.preferred_break_minutes if profile else None,
        "planning_intensity": profile.planning_intensity if profile else None,
        "workday_start": _serialize_time(profile.workday_start) if profile else None,
        "workday_end": _serialize_time(profile.workday_end) if profile else None,
        "avoid_after_time": _serialize_time(profile.avoid_after_time) if profile else None,
        "regular_commitments": profile.regular_commitments() if profile else [],
        "priorities": profile.priorities() if profile else [],
        "overload_behavior": profile.overload_behavior if profile else None,
        "usage": {key: list(value) for key, value in FIELD_USAGE.items()},
        "privacy": {
            "notice_version": NOTICE_VERSION,
            "account_private": True,
            "web_search_excluded": True,
            "message": "These optional preferences are stored with your V-SPACE account and used only when relevant to personalize product features. V1 does not send this life-context profile to web search providers.",
        },
        "updated_at": profile.updated_at.isoformat() if profile and profile.updated_at else None,
    })
    return base


def personalization_summary_for_user(user: User) -> dict[str, Any]:
    return serialize_summary(profile_for_user(user))


def save_profile(*, user: User, payload: dict[str, Any] | None) -> UserPersonalizationProfile:
    raw = payload if isinstance(payload, dict) else {}
    profile = get_or_create_profile(user)

    wake = _parse_optional_time(raw.get("usual_wake_time"), field_label="wake")
    sleep = _parse_optional_time(raw.get("usual_sleep_time"), field_label="sleep")
    work_start = _parse_optional_time(raw.get("workday_start"), field_label="focused-work start")
    work_end = _parse_optional_time(raw.get("workday_end"), field_label="focused-work end")
    avoid_after = _parse_optional_time(raw.get("avoid_after_time"), field_label="avoid-after")
    if work_start and work_end and work_end <= work_start:
        raise PersonalizationValidationError("Your focused-work end must be after its start.")
    if work_start and work_end:
        minutes = int((datetime.combine(date.today(), work_end) - datetime.combine(date.today(), work_start)).total_seconds() // 60)
        if minutes < 120:
            raise PersonalizationValidationError("Give V-SPACE at least a 2-hour focused-work window.")

    profile.usual_wake_time = wake
    profile.usual_sleep_time = sleep
    profile.productive_period = _choice(raw.get("productive_period"), PRODUCTIVE_PERIODS, field_label="productive period")
    profile.preferred_focus_minutes = _int_choice(raw.get("preferred_focus_minutes"), VALID_FOCUS_MINUTES, field_label="focus length")
    profile.preferred_break_minutes = _int_choice(raw.get("preferred_break_minutes"), VALID_BREAK_MINUTES, field_label="break length")
    profile.planning_intensity = _choice(raw.get("planning_intensity"), PLANNING_INTENSITIES, field_label="planning intensity")
    profile.workday_start = work_start
    profile.workday_end = work_end
    profile.avoid_after_time = avoid_after
    profile.set_regular_commitments(_normalize_commitments(raw.get("regular_commitments")))
    profile.set_priorities(_normalize_priorities(raw.get("priorities")))
    profile.overload_behavior = _choice(raw.get("overload_behavior"), OVERLOAD_BEHAVIORS, field_label="overload behavior")
    profile.onboarding_state = "completed"
    profile.completed_at = datetime.utcnow()
    profile.deferred_at = None
    profile.data_use_notice_version = NOTICE_VERSION
    profile.data_use_acknowledged_at = datetime.utcnow()
    try:
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise PersonalizationPersistenceError("V-SPACE could not save your personalization profile.") from error
    return profile


def defer_profile(*, user: User) -> UserPersonalizationProfile:
    profile = get_or_create_profile(user)
    if profile.onboarding_state != "completed":
        profile.onboarding_state = "deferred"
        profile.deferred_at = datetime.utcnow()
    try:
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise PersonalizationPersistenceError("V-SPACE could not defer personalization right now.") from error
    return profile


def clear_profile(*, user: User) -> UserPersonalizationProfile:
    profile = get_or_create_profile(user)
    for field in (
        "usual_wake_time", "usual_sleep_time", "productive_period", "preferred_focus_minutes",
        "preferred_break_minutes", "planning_intensity", "workday_start", "workday_end",
        "avoid_after_time", "overload_behavior", "completed_at", "data_use_acknowledged_at",
    ):
        setattr(profile, field, None)
    profile.set_regular_commitments([])
    profile.set_priorities([])
    profile.onboarding_state = "deferred"
    profile.deferred_at = datetime.utcnow()
    profile.data_use_notice_version = NOTICE_VERSION
    try:
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise PersonalizationPersistenceError("V-SPACE could not clear your personalization profile.") from error
    return profile


def _human_time(value: time | None) -> str | None:
    if value is None:
        return None
    hour = value.hour % 12 or 12
    return f"{hour}:{value.minute:02d} {'PM' if value.hour >= 12 else 'AM'}"


def planner_defaults_for_user(owner_id: int) -> dict[str, Any]:
    """Return deterministic planner defaults plus transparent profile reasons.

    Availability and energy are intentionally separate. Wake/sleep and explicit
    work windows define when planning may happen; productive period influences
    where cognitively demanding work is *preferred* inside that window.
    """
    profile = profile_for_user(int(owner_id))
    default_start = time(9, 0)
    default_end = time(17, 0)
    default_break = 15
    if profile is None:
        return {
            "working_start": "09:00", "working_end": "17:00", "break_minutes": 15,
            "preferred_focus_minutes": 60, "energy_mode": "normal", "capacity_factor": 1.0,
            "productive_period": None, "preferred_window_start": None, "preferred_window_end": None,
            "usual_wake_time": None, "usual_sleep_time": None, "avoid_after_time": None,
            "priorities": [], "overload_behavior": "leave_unscheduled", "explanations": [],
            "sources": {
                "working_start": "default", "working_end": "default", "break_minutes": "default",
                "energy_mode": "default", "preferred_focus_minutes": "default", "productive_period": "default",
            },
        }

    explanations: list[str] = []
    productive_period = str(profile.productive_period or "").strip() or None
    productive_windows = {
        "morning": (time(8, 0), time(12, 0)),
        "afternoon": (time(12, 0), time(17, 0)),
        "evening": (time(17, 0), time(22, 0)),
        "late_night": (time(20, 0), time(23, 59)),
        "varies": (None, None),
    }
    preferred_window_start, preferred_window_end = productive_windows.get(productive_period or "", (None, None))

    # Availability starts from explicit profile boundaries when present, then
    # falls back to wake/sleep context. Productive time is not treated as the
    # whole available day; it is only a placement preference.
    start_at = profile.workday_start or default_start
    end_at = profile.workday_end or default_end
    start_source = "profile" if profile.workday_start else "default"
    end_source = "profile" if profile.workday_end else "default"

    if profile.workday_start is None and profile.usual_wake_time:
        total = profile.usual_wake_time.hour * 60 + profile.usual_wake_time.minute + 30
        total = min(total, 22 * 60)
        start_at = time(total // 60, total % 60)
        start_source = "profile"
        explanations.append(
            f"Focused work starts around {_human_time(start_at)} because your usual wake time is {_human_time(profile.usual_wake_time)}."
        )
    elif profile.workday_start:
        explanations.append(f"Your usual focused-work window starts at {_human_time(profile.workday_start)}.")

    if profile.workday_end is None and profile.usual_sleep_time:
        sleep = profile.usual_sleep_time
        # The current planner stores same-day time ranges. For after-midnight
        # sleepers, stop conservatively at 11:30 PM instead of pretending the
        # next calendar day is part of the same plan block.
        if 0 <= sleep.hour <= 4:
            end_at = time(23, 30)
        elif sleep.hour >= 18:
            total = sleep.hour * 60 + sleep.minute - 30
            end_at = time(max(total, 0) // 60, max(total, 0) % 60)
        end_source = "profile"
        explanations.append(
            f"Late work is limited before your usual {_human_time(sleep)} sleep time unless you override it."
        )
    elif profile.workday_end:
        explanations.append(f"Your usual focused-work window ends at {_human_time(profile.workday_end)}.")

    # When the user supplied only an energy preference, keep the window broad
    # enough to actually include that preferred period.
    if profile.workday_end is None and profile.usual_sleep_time is None and preferred_window_end:
        end_at = max(end_at, preferred_window_end)
        end_source = "profile"
    if profile.workday_start is None and profile.usual_wake_time is None and preferred_window_start:
        start_at = min(start_at, preferred_window_start)
        start_source = "profile"

    if profile.avoid_after_time and profile.avoid_after_time > start_at:
        end_at = min(end_at, profile.avoid_after_time)
        end_source = "profile"
        explanations.append(f"Nothing is normally scheduled after {_human_time(profile.avoid_after_time)} because you asked V-SPACE to avoid that time.")

    # Preserve the scheduler's same-day and <=16-hour invariants.
    if end_at <= start_at:
        start_at, end_at, start_source, end_source = default_start, default_end, "default", "default"
    minutes = int((datetime.combine(date.today(), end_at) - datetime.combine(date.today(), start_at)).total_seconds() // 60)
    if minutes > 16 * 60:
        capped = datetime.combine(date.today(), start_at) + timedelta(hours=16)
        end_at = capped.time().replace(second=0, microsecond=0)
        explanations.append("The usable planning window was capped at 16 hours for safety.")

    intensity = str(profile.planning_intensity or "").strip() or None
    energy = "light" if intensity == "light" else "intense" if intensity == "intense" else "normal"
    capacity_factor = {"light": 0.65, "balanced": 0.80, "productive": 0.92, "intense": 1.0}.get(intensity or "", 1.0)
    if intensity:
        label = {
            "light": "breathing room", "balanced": "a realistic amount of open space",
            "productive": "most of your available time", "intense": "nearly all available time",
        }.get(intensity, "a realistic amount of open space")
        explanations.append(f"Your normal planning style keeps {label} in the day.")
    if productive_period and productive_period != "varies":
        explanations.append(f"Harder focus work is preferred in the {productive_period.replace('_', ' ')} because that is when you said you concentrate best.")
    if profile.preferred_focus_minutes:
        explanations.append(f"Long focus requests are split toward {int(profile.preferred_focus_minutes)}-minute blocks when possible.")
    if profile.preferred_break_minutes:
        explanations.append(f"V-SPACE uses your preferred {int(profile.preferred_break_minutes)}-minute break between blocks.")

    return {
        "working_start": start_at.strftime("%H:%M"),
        "working_end": end_at.strftime("%H:%M"),
        "break_minutes": int(profile.preferred_break_minutes or default_break),
        "preferred_focus_minutes": int(profile.preferred_focus_minutes or 60),
        "energy_mode": energy,
        "capacity_factor": float(capacity_factor),
        "productive_period": productive_period,
        "preferred_window_start": preferred_window_start.strftime("%H:%M") if preferred_window_start else None,
        "preferred_window_end": preferred_window_end.strftime("%H:%M") if preferred_window_end else None,
        "usual_wake_time": _serialize_time(profile.usual_wake_time),
        "usual_sleep_time": _serialize_time(profile.usual_sleep_time),
        "avoid_after_time": _serialize_time(profile.avoid_after_time),
        "priorities": profile.priorities(),
        "overload_behavior": str(profile.overload_behavior or "leave_unscheduled"),
        "explanations": explanations[:8],
        "sources": {
            "working_start": start_source,
            "working_end": end_source,
            "break_minutes": "profile" if profile.preferred_break_minutes else "default",
            "energy_mode": "profile" if profile.planning_intensity else "default",
            "preferred_focus_minutes": "profile" if profile.preferred_focus_minutes else "default",
            "productive_period": "profile" if productive_period else "default",
        },
    }


def recurring_commitments_for_range(*, owner_id: int, start_date: date, end_date: date) -> list[dict[str, Any]]:
    profile = profile_for_user(int(owner_id))
    if profile is None:
        return []
    rules = profile.regular_commitments()
    if not rules:
        return []
    result: list[dict[str, Any]] = []
    cursor = start_date
    while cursor <= end_date:
        weekday = cursor.weekday()
        for index, rule in enumerate(rules):
            if weekday not in list(rule.get("days") or []):
                continue
            result.append({
                "id": f"profile-{index + 1}-{cursor.isoformat()}",
                "title": str(rule.get("title") or "Regular commitment")[:80],
                "date": cursor.isoformat(),
                "start_time": str(rule.get("start_time") or "09:00"),
                "end_time": str(rule.get("end_time") or "10:00"),
                "commitment_type": str(rule.get("commitment_type") or "other"),
                "notes": "From your V-SPACE Profile. Edit it in Settings → Personalization.",
                "source": "profile",
                "editable": False,
            })
        cursor += timedelta(days=1)
    return result


def selective_context_for_feature(*, owner_id: int, feature: str) -> dict[str, Any]:
    """Return only profile fields approved for one product feature.

    V1 currently uses this for deterministic product features. Callers must not
    forward the result to web-search providers.
    """
    profile = profile_for_user(int(owner_id))
    if profile is None:
        return {}
    normalized = str(feature or "").strip().casefold()
    if normalized == "smart_planner":
        return {
            "usual_wake_time": _serialize_time(profile.usual_wake_time),
            "usual_sleep_time": _serialize_time(profile.usual_sleep_time),
            "productive_period": profile.productive_period,
            "preferred_focus_minutes": profile.preferred_focus_minutes,
            "preferred_break_minutes": profile.preferred_break_minutes,
            "planning_intensity": profile.planning_intensity,
            "workday_start": _serialize_time(profile.workday_start),
            "workday_end": _serialize_time(profile.workday_end),
            "avoid_after_time": _serialize_time(profile.avoid_after_time),
            "overload_behavior": profile.overload_behavior,
            "priorities": profile.priorities(),
        }
    if normalized == "focus_studio":
        return {
            "productive_period": profile.productive_period,
            "preferred_focus_minutes": profile.preferred_focus_minutes,
            "preferred_break_minutes": profile.preferred_break_minutes,
        }
    if normalized in {"dashboard", "ask_vspace"}:
        return {"priorities": profile.priorities()}
    return {}

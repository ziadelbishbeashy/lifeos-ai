"""I21 academic schedule service for module assessments.

The service owns validation, ownership checks, persistence, and deterministic
schedule facts. API/UI layers should not write ModuleAssessment rows directly.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import ModuleAssessment
from services.module_service import ModuleNotFoundError, require_owned_module


ASSESSMENT_TYPES = (
    "Quiz",
    "Assignment",
    "Midterm",
    "Final",
    "Project",
    "Presentation",
    "Lab",
    "Other",
)
ASSESSMENT_STATUSES = ("Upcoming", "In Progress", "Completed", "Cancelled")


class ModuleAssessmentError(RuntimeError):
    pass


class ModuleAssessmentNotFoundError(ModuleAssessmentError, LookupError):
    pass


class ModuleAssessmentValidationError(ModuleAssessmentError, ValueError):
    pass


class ModuleAssessmentPersistenceError(ModuleAssessmentError):
    pass


def _clean_optional_text(value: Any, *, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    if max_length is not None and len(cleaned) > max_length:
        raise ModuleAssessmentValidationError(
            f"Value cannot exceed {max_length} characters."
        )
    return cleaned


def _parse_date(value: Any, field_name: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ModuleAssessmentValidationError(
            f"{field_name} must use YYYY-MM-DD format."
        ) from error


def _parse_time(value: Any, field_name: str) -> time | None:
    if value in (None, ""):
        return None
    if isinstance(value, time):
        return value
    try:
        return time.fromisoformat(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ModuleAssessmentValidationError(
            f"{field_name} must use HH:MM or HH:MM:SS format."
        ) from error


def _parse_weight(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        weight = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ModuleAssessmentValidationError(
            "weight_percent must be a valid number."
        ) from error
    if weight < 0 or weight > 100:
        raise ModuleAssessmentValidationError(
            "weight_percent must be between 0 and 100."
        )
    return weight.quantize(Decimal("0.01"))


def _parse_estimated_minutes(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        minutes = int(value)
    except (TypeError, ValueError) as error:
        raise ModuleAssessmentValidationError(
            "estimated_study_minutes must be a whole number."
        ) from error
    if minutes < 0:
        raise ModuleAssessmentValidationError(
            "estimated_study_minutes cannot be negative."
        )
    if minutes > 100_000:
        raise ModuleAssessmentValidationError(
            "estimated_study_minutes is too large."
        )
    return minutes


def _normalize_type(value: Any) -> str:
    cleaned = str(value or "").strip()
    if cleaned not in ASSESSMENT_TYPES:
        raise ModuleAssessmentValidationError(
            f"assessment_type must be one of: {', '.join(ASSESSMENT_TYPES)}."
        )
    return cleaned


def _normalize_status(value: Any) -> str:
    cleaned = str(value or "Upcoming").strip()
    if cleaned not in ASSESSMENT_STATUSES:
        raise ModuleAssessmentValidationError(
            f"status must be one of: {', '.join(ASSESSMENT_STATUSES)}."
        )
    return cleaned


def _normalize_title(value: Any) -> str:
    title = str(value or "").strip()
    if not title:
        raise ModuleAssessmentValidationError("Assessment title is required.")
    if len(title) > 180:
        raise ModuleAssessmentValidationError(
            "Assessment title cannot exceed 180 characters."
        )
    return title


def _commit(row: ModuleAssessment, message: str) -> ModuleAssessment:
    try:
        db.session.add(row)
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise ModuleAssessmentPersistenceError(message) from error
    return row


def require_owned_assessment(
    *, assessment_id: int, user_id: int, module_id: int | None = None
) -> ModuleAssessment:
    assessment = db.session.get(ModuleAssessment, int(assessment_id))
    if assessment is None:
        raise ModuleAssessmentNotFoundError("Assessment not found.")
    try:
        require_owned_module(assessment.module_id, user_id)
    except ModuleNotFoundError as error:
        # Deliberately hide whether another user's row exists.
        raise ModuleAssessmentNotFoundError("Assessment not found.") from error
    if module_id is not None and assessment.module_id != int(module_id):
        raise ModuleAssessmentNotFoundError("Assessment not found.")
    return assessment


def list_owned_module_assessments(
    *, module_id: int, user_id: int
) -> list[ModuleAssessment]:
    module = require_owned_module(module_id, user_id)
    return (
        ModuleAssessment.query
        .filter_by(module_id=module.id)
        .order_by(
            ModuleAssessment.assessment_date.asc(),
            ModuleAssessment.due_date.asc(),
            ModuleAssessment.id.asc(),
        )
        .all()
    )


def create_owned_module_assessment(
    *,
    module_id: int,
    user_id: int,
    title: Any,
    assessment_type: Any,
    assessment_date: Any = None,
    assessment_time: Any = None,
    due_date: Any = None,
    due_time: Any = None,
    weight_percent: Any = None,
    status: Any = "Upcoming",
    topics: Any = None,
    estimated_study_minutes: Any = None,
    notes: Any = None,
) -> ModuleAssessment:
    module = require_owned_module(module_id, user_id)
    assessment = ModuleAssessment(
        module_id=module.id,
        title=_normalize_title(title),
        assessment_type=_normalize_type(assessment_type),
        assessment_date=_parse_date(assessment_date, "assessment_date"),
        assessment_time=_parse_time(assessment_time, "assessment_time"),
        due_date=_parse_date(due_date, "due_date"),
        due_time=_parse_time(due_time, "due_time"),
        weight_percent=_parse_weight(weight_percent),
        status=_normalize_status(status),
        topics=_clean_optional_text(topics),
        estimated_study_minutes=_parse_estimated_minutes(estimated_study_minutes),
        notes=_clean_optional_text(notes),
    )
    return _commit(assessment, "LifeOS could not create the assessment.")


def update_owned_module_assessment(
    *,
    assessment_id: int,
    user_id: int,
    module_id: int | None = None,
    changes: dict[str, Any],
) -> ModuleAssessment:
    assessment = require_owned_assessment(
        assessment_id=assessment_id,
        user_id=user_id,
        module_id=module_id,
    )
    allowed = {
        "title",
        "assessment_type",
        "assessment_date",
        "assessment_time",
        "due_date",
        "due_time",
        "weight_percent",
        "status",
        "topics",
        "estimated_study_minutes",
        "notes",
    }
    unknown = set(changes) - allowed
    if unknown:
        raise ModuleAssessmentValidationError(
            f"Unsupported assessment fields: {', '.join(sorted(unknown))}."
        )

    if "title" in changes:
        assessment.title = _normalize_title(changes.get("title"))
    if "assessment_type" in changes:
        assessment.assessment_type = _normalize_type(changes.get("assessment_type"))
    if "assessment_date" in changes:
        assessment.assessment_date = _parse_date(changes.get("assessment_date"), "assessment_date")
    if "assessment_time" in changes:
        assessment.assessment_time = _parse_time(changes.get("assessment_time"), "assessment_time")
    if "due_date" in changes:
        assessment.due_date = _parse_date(changes.get("due_date"), "due_date")
    if "due_time" in changes:
        assessment.due_time = _parse_time(changes.get("due_time"), "due_time")
    if "weight_percent" in changes:
        assessment.weight_percent = _parse_weight(changes.get("weight_percent"))
    if "status" in changes:
        assessment.status = _normalize_status(changes.get("status"))
    if "topics" in changes:
        assessment.topics = _clean_optional_text(changes.get("topics"))
    if "estimated_study_minutes" in changes:
        assessment.estimated_study_minutes = _parse_estimated_minutes(
            changes.get("estimated_study_minutes")
        )
    if "notes" in changes:
        assessment.notes = _clean_optional_text(changes.get("notes"))
    assessment.updated_at = datetime.utcnow()
    return _commit(assessment, "LifeOS could not update the assessment.")


def delete_owned_module_assessment(
    *, assessment_id: int, user_id: int, module_id: int | None = None
) -> str:
    assessment = require_owned_assessment(
        assessment_id=assessment_id,
        user_id=user_id,
        module_id=module_id,
    )
    title = assessment.title
    try:
        db.session.delete(assessment)
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise ModuleAssessmentPersistenceError(
            "LifeOS could not delete the assessment."
        ) from error
    return title


def assessment_target_date(assessment: ModuleAssessment) -> date | None:
    """Return the authoritative date used for schedule ordering/countdowns."""
    if assessment.assessment_type == "Assignment":
        return assessment.due_date or assessment.assessment_date
    return assessment.assessment_date or assessment.due_date


def days_until_assessment(
    assessment: ModuleAssessment, *, today: date | None = None
) -> int | None:
    target = assessment_target_date(assessment)
    if target is None:
        return None
    return (target - (today or date.today())).days


def assessment_timing_label(
    assessment: ModuleAssessment, *, today: date | None = None
) -> str | None:
    if assessment.status in {"Completed", "Cancelled"}:
        return assessment.status
    days = days_until_assessment(assessment, today=today)
    if days is None:
        return None
    if days < 0:
        return "Overdue"
    if days == 0:
        return "Today"
    if days == 1:
        return "Tomorrow"
    if days <= 7:
        return "This week"
    return "Upcoming"

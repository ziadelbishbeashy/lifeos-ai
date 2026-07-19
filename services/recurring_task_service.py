from calendar import monthrange
from datetime import date, datetime, timedelta

from database import db
from models import Task


VALID_RECURRENCE_TYPES = {"daily", "weekly", "monthly", "custom_days"}


def add_months(source_date: date, months: int) -> date:
    """Return source_date moved forward by the requested number of months."""
    month_index = source_date.month - 1 + months
    year = source_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(source_date.day, monthrange(year, month)[1])
    return date(year, month, day)


def calculate_next_date(current_date, recurrence_type, recurrence_interval=1):
    if not current_date:
        current_date = date.today()

    interval = max(int(recurrence_interval or 1), 1)

    if recurrence_type == "daily":
        return current_date + timedelta(days=interval)
    if recurrence_type == "weekly":
        return current_date + timedelta(weeks=interval)
    if recurrence_type == "monthly":
        return add_months(current_date, interval)
    if recurrence_type == "custom_days":
        return current_date + timedelta(days=interval)

    raise ValueError("Unsupported recurrence type.")


def copy_shifted_reminder(task, next_deadline):
    if not task.reminder_enabled or not task.reminder_datetime:
        return None

    base_date = task.deadline or task.reminder_datetime.date()
    day_shift = (next_deadline - base_date).days
    return task.reminder_datetime + timedelta(days=day_shift)


def generate_next_occurrence(task):
    """
    Create exactly one next occurrence for a completed recurring task.
    Returns the new task, or None when recurrence has ended/already generated.
    """
    if not task.is_recurring or task.recurrence_type not in VALID_RECURRENCE_TYPES:
        return None

    existing = Task.query.filter_by(recurrence_parent_id=task.id).first()
    if existing:
        return existing

    base_date = task.deadline or date.today()
    next_date = calculate_next_date(
        base_date,
        task.recurrence_type,
        task.recurrence_interval,
    )

    if task.recurrence_end_date and next_date > task.recurrence_end_date:
        task.next_occurrence_date = None
        task.last_generated_at = datetime.utcnow()
        return None

    next_task = Task(
        user_id=task.user_id,
        project_id=task.project_id,
        title=task.title,
        description=task.description,
        module=task.module,
        importance=task.importance,
        difficulty=task.difficulty,
        deadline=next_date,
        status="Pending",
        priority_score=task.priority_score,
        reason=task.reason,
        reminder_enabled=task.reminder_enabled,
        reminder_type=task.reminder_type,
        reminder_datetime=copy_shifted_reminder(task, next_date),
        last_reminder_sent_at=None,
        is_recurring=True,
        recurrence_type=task.recurrence_type,
        recurrence_interval=task.recurrence_interval,
        recurrence_end_date=task.recurrence_end_date,
        recurrence_parent_id=task.id,
        recurrence_series_id=task.recurrence_series_id or task.id,
        next_occurrence_date=calculate_next_date(
            next_date,
            task.recurrence_type,
            task.recurrence_interval,
        ),
    )

    task.last_generated_at = datetime.utcnow()
    task.next_occurrence_date = next_date
    db.session.add(next_task)
    return next_task

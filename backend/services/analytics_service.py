from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable

from models import FocusSession, Project, Task


COMPLETED_STATUS = "Completed"
ACTIVE_PROJECT_STATUSES = {"In Progress", "Planning", "Active"}


@dataclass(frozen=True)
class AnalyticsRange:
    key: str
    label: str
    start_date: date
    end_date: date
    previous_start: date
    previous_end: date

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def resolve_analytics_range(
    period: str | None,
    start_value: str | None = None,
    end_value: str | None = None,
    today: date | None = None,
) -> AnalyticsRange:
    today = today or date.today()
    period = (period or "month").lower()

    if period == "today":
        start_date = today
        end_date = today
        label = "Today"

    elif period == "week":
        start_date = today - timedelta(days=today.weekday())
        end_date = today
        label = "This week"

    elif period == "30d":
        start_date = today - timedelta(days=29)
        end_date = today
        label = "Last 30 days"

    elif period == "90d":
        start_date = today - timedelta(days=89)
        end_date = today
        label = "Last 90 days"

    elif period == "custom":
        start_date = _parse_date(start_value) or today - timedelta(days=29)
        end_date = _parse_date(end_value) or today

        if start_date > end_date:
            start_date, end_date = end_date, start_date

        # Keep the page responsive even when a very large accidental range is entered.
        if (end_date - start_date).days > 730:
            start_date = end_date - timedelta(days=730)

        label = f"{start_date.strftime('%d %b %Y')} – {end_date.strftime('%d %b %Y')}"

    else:
        period = "month"
        start_date = today.replace(day=1)
        end_date = today
        label = "This month"

    day_count = (end_date - start_date).days + 1
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=day_count - 1)

    return AnalyticsRange(
        key=period,
        label=label,
        start_date=start_date,
        end_date=end_date,
        previous_start=previous_start,
        previous_end=previous_end,
    )


def _date_from_datetime(value: datetime | None) -> date | None:
    return value.date() if value else None


def _in_range(value: date | datetime | None, start_date: date, end_date: date) -> bool:
    if value is None:
        return False

    value_date = value.date() if isinstance(value, datetime) else value
    return start_date <= value_date <= end_date


def _percent_change(current: int | float, previous: int | float) -> dict:
    current = current or 0
    previous = previous or 0

    if previous == 0:
        if current == 0:
            return {"value": 0, "direction": "flat", "label": "No change"}
        return {"value": 100, "direction": "up", "label": "New activity"}

    change = round(((current - previous) / previous) * 100)

    if change > 0:
        direction = "up"
    elif change < 0:
        direction = "down"
    else:
        direction = "flat"

    return {
        "value": abs(change),
        "direction": direction,
        "label": f"{abs(change)}% {'higher' if change > 0 else 'lower' if change < 0 else 'unchanged'}",
    }


def _format_minutes(total_minutes: int) -> str:
    total_minutes = max(int(total_minutes or 0), 0)
    hours, minutes = divmod(total_minutes, 60)

    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def _build_buckets(start_date: date, end_date: date) -> list[dict]:
    total_days = (end_date - start_date).days + 1
    buckets: list[dict] = []

    if total_days <= 14:
        cursor = start_date
        while cursor <= end_date:
            buckets.append({
                "start": cursor,
                "end": cursor,
                "label": cursor.strftime("%a") if total_days <= 7 else cursor.strftime("%d %b"),
                "title": cursor.strftime("%d %B %Y"),
            })
            cursor += timedelta(days=1)
        return buckets

    if total_days <= 120:
        cursor = start_date
        index = 1
        while cursor <= end_date:
            bucket_end = min(cursor + timedelta(days=6), end_date)
            buckets.append({
                "start": cursor,
                "end": bucket_end,
                "label": f"W{index}",
                "title": f"{cursor.strftime('%d %b')} – {bucket_end.strftime('%d %b')}",
            })
            cursor = bucket_end + timedelta(days=1)
            index += 1
        return buckets

    cursor = start_date.replace(day=1)
    while cursor <= end_date:
        last_day = monthrange(cursor.year, cursor.month)[1]
        month_end = date(cursor.year, cursor.month, last_day)
        bucket_start = max(cursor, start_date)
        bucket_end = min(month_end, end_date)
        buckets.append({
            "start": bucket_start,
            "end": bucket_end,
            "label": cursor.strftime("%b %y"),
            "title": cursor.strftime("%B %Y"),
        })
        cursor = month_end + timedelta(days=1)

    return buckets


def _task_bucket_series(tasks: Iterable[Task], buckets: list[dict]) -> list[dict]:
    rows = []

    for bucket in buckets:
        created_count = sum(
            1 for task in tasks
            if _in_range(task.created_at, bucket["start"], bucket["end"])
        )
        completed_count = sum(
            1 for task in tasks
            if _in_range(task.completed_at, bucket["start"], bucket["end"])
        )
        rows.append({
            **bucket,
            "created": created_count,
            "completed": completed_count,
        })

    maximum = max(
        [row["created"] for row in rows] + [row["completed"] for row in rows] + [1]
    )

    for row in rows:
        row["created_height"] = round((row["created"] / maximum) * 100)
        row["completed_height"] = round((row["completed"] / maximum) * 100)

    return rows


def _focus_bucket_series(sessions: Iterable[FocusSession], buckets: list[dict]) -> list[dict]:
    rows = []

    for bucket in buckets:
        matching = [
            session for session in sessions
            if _in_range(session.completed_at, bucket["start"], bucket["end"])
        ]
        minutes = sum(session.actual_minutes or 0 for session in matching)
        rows.append({
            **bucket,
            "minutes": minutes,
            "sessions": len(matching),
        })

    maximum = max([row["minutes"] for row in rows] + [1])

    for row in rows:
        row["height"] = round((row["minutes"] / maximum) * 100)
        row["formatted"] = _format_minutes(row["minutes"])

    return rows


def _status_distribution(tasks: list[Task]) -> dict:
    ordered_statuses = ["Completed", "In Progress", "Pending", "Blocked"]
    color_map = {
        "Completed": "var(--app-green)",
        "In Progress": "var(--app-primary)",
        "Pending": "var(--app-yellow)",
        "Blocked": "var(--app-red)",
    }
    counts = {status: 0 for status in ordered_statuses}

    for task in tasks:
        status = task.status if task.status in counts else "Pending"
        counts[status] += 1

    total = max(len(tasks), 1)
    cursor = 0.0
    segments = []
    gradient_parts = []

    for status in ordered_statuses:
        count = counts[status]
        percentage = round((count / total) * 100, 1) if tasks else 0
        start = cursor
        end = cursor + percentage
        cursor = end

        segments.append({
            "name": status,
            "count": count,
            "percentage": percentage,
            "color": color_map[status],
        })

        if percentage:
            gradient_parts.append(f"{color_map[status]} {start}% {end}%")

    gradient = (
        f"conic-gradient({', '.join(gradient_parts)})"
        if gradient_parts
        else "conic-gradient(var(--app-border-strong) 0 100%)"
    )

    return {
        "segments": segments,
        "gradient": gradient,
        "total": len(tasks),
    }


def _priority_distribution(tasks: list[Task]) -> list[dict]:
    priorities = ["Critical", "High", "Medium", "Low"]
    colors = {
        "Critical": "var(--app-red)",
        "High": "#ff9f6e",
        "Medium": "var(--app-yellow)",
        "Low": "var(--app-cyan)",
    }
    open_tasks = [task for task in tasks if task.status != COMPLETED_STATUS]
    counts = {priority: 0 for priority in priorities}

    for task in open_tasks:
        priority = task.importance if task.importance in counts else "Medium"
        counts[priority] += 1

    maximum = max(list(counts.values()) + [1])

    return [
        {
            "name": priority,
            "count": counts[priority],
            "width": round((counts[priority] / maximum) * 100),
            "color": colors[priority],
        }
        for priority in priorities
    ]


def _project_focus_data(sessions: list[FocusSession]) -> list[dict]:
    totals: dict[str, int] = defaultdict(int)

    for session in sessions:
        project_name = "General workspace"
        if session.task and session.task.project:
            project_name = session.task.project.title
        totals[project_name] += session.actual_minutes or 0

    rows = sorted(
        ({"name": name, "minutes": minutes} for name, minutes in totals.items()),
        key=lambda row: row["minutes"],
        reverse=True,
    )[:7]

    maximum = max([row["minutes"] for row in rows] + [1])
    for row in rows:
        row["width"] = round((row["minutes"] / maximum) * 100)
        row["formatted"] = _format_minutes(row["minutes"])

    return rows


def _project_rows(
    projects: list[Project],
    tasks: list[Task],
    sessions_in_period: list[FocusSession],
) -> list[dict]:
    today = date.today()
    tasks_by_project: dict[int, list[Task]] = defaultdict(list)
    focus_by_project: dict[int, int] = defaultdict(int)

    for task in tasks:
        if task.project_id:
            tasks_by_project[task.project_id].append(task)

    for session in sessions_in_period:
        if session.task and session.task.project_id:
            focus_by_project[session.task.project_id] += session.actual_minutes or 0

    rows = []

    for project in projects:
        project_tasks = tasks_by_project.get(project.id, [])
        completed = sum(1 for task in project_tasks if task.status == COMPLETED_STATUS)
        open_count = len(project_tasks) - completed
        overdue = sum(
            1 for task in project_tasks
            if task.deadline and task.deadline < today and task.status != COMPLETED_STATUS
        )
        blocked = sum(1 for task in project_tasks if task.status == "Blocked")
        task_progress = round((completed / len(project_tasks)) * 100) if project_tasks else 0
        display_progress = task_progress if project_tasks else (project.progress or 0)

        if project.deadline:
            days_remaining = (project.deadline - today).days
            if days_remaining < 0:
                deadline_label = f"{abs(days_remaining)}d overdue"
                deadline_tone = "danger"
            elif days_remaining == 0:
                deadline_label = "Due today"
                deadline_tone = "warning"
            else:
                deadline_label = f"{days_remaining}d left"
                deadline_tone = "neutral"
        else:
            days_remaining = None
            deadline_label = "No deadline"
            deadline_tone = "muted"

        rows.append({
            "id": project.id,
            "title": project.title,
            "status": project.status or "In Progress",
            "priority": project.priority or "Medium",
            "progress": display_progress,
            "task_progress": task_progress,
            "total_tasks": len(project_tasks),
            "completed_tasks": completed,
            "open_tasks": open_count,
            "overdue_tasks": overdue,
            "blocked_tasks": blocked,
            "focus_minutes": focus_by_project.get(project.id, 0),
            "focus_label": _format_minutes(focus_by_project.get(project.id, 0)),
            "deadline_label": deadline_label,
            "deadline_tone": deadline_tone,
            "days_remaining": days_remaining,
            "deadline": project.deadline,
        })

    return sorted(
        rows,
        key=lambda row: (
            row["status"] in ("Completed", "Paused"),
            -row["overdue_tasks"],
            row["deadline"] or date.max,
            -row["focus_minutes"],
        ),
    )


def _build_insights(
    *,
    completed_in_period: int,
    completed_previous: int,
    focus_minutes: int,
    focus_previous: int,
    overdue_count: int,
    blocked_count: int,
    focus_by_project: list[dict],
    focus_series: list[dict],
    created_in_period: int,
) -> list[dict]:
    insights = []

    completion_change = _percent_change(completed_in_period, completed_previous)
    if completion_change["direction"] == "up":
        insights.append({
            "tone": "positive",
            "title": "Task throughput improved",
            "text": f"You completed {completed_in_period} task(s), {completion_change['label']} than the previous period.",
        })
    elif completion_change["direction"] == "down":
        insights.append({
            "tone": "attention",
            "title": "Task completion slowed",
            "text": f"You completed {completed_in_period} task(s), {completion_change['label']} than the previous period.",
        })

    focus_change = _percent_change(focus_minutes, focus_previous)
    if focus_minutes:
        insights.append({
            "tone": "positive" if focus_change["direction"] != "down" else "neutral",
            "title": "Focused work recorded",
            "text": f"You logged {_format_minutes(focus_minutes)} of focus time. That is {focus_change['label']} than the previous period.",
        })

    if overdue_count:
        insights.append({
            "tone": "danger",
            "title": "Overdue work needs attention",
            "text": f"{overdue_count} open task(s) are past their deadline. Review or reschedule them before adding more work.",
        })

    if blocked_count:
        insights.append({
            "tone": "attention",
            "title": "Blocked tasks are limiting progress",
            "text": f"{blocked_count} task(s) are blocked. Record the blocker and define the next action for each one.",
        })

    if focus_by_project:
        top_project = focus_by_project[0]
        insights.append({
            "tone": "neutral",
            "title": "Most focused area",
            "text": f"{top_project['name']} received the most focus time with {top_project['formatted']}.",
        })

    if focus_series:
        best = max(focus_series, key=lambda row: row["minutes"])
        if best["minutes"]:
            insights.append({
                "tone": "neutral",
                "title": "Strongest focus window",
                "text": f"Your best period was {best['title']} with {best['formatted']} of focused work.",
            })

    if created_in_period > completed_in_period and created_in_period >= 3:
        insights.append({
            "tone": "attention",
            "title": "The task list is growing",
            "text": f"You created {created_in_period} task(s) and completed {completed_in_period}. Consider clearing existing work before expanding the backlog.",
        })

    if not insights:
        insights.append({
            "tone": "neutral",
            "title": "More activity will unlock trends",
            "text": "Complete tasks and focus sessions to build a clearer productivity picture.",
        })

    return insights[:6]


def get_analytics_dashboard(
    user_id: int,
    period: str | None = "month",
    start_value: str | None = None,
    end_value: str | None = None,
) -> dict:
    selected_range = resolve_analytics_range(period, start_value, end_value)

    tasks = (
        Task.query
        .filter_by(user_id=user_id)
        .order_by(Task.created_at.asc())
        .all()
    )
    projects = (
        Project.query
        .filter_by(user_id=user_id)
        .order_by(Project.created_at.asc())
        .all()
    )
    completed_sessions = (
        FocusSession.query
        .filter_by(user_id=user_id, status="completed")
        .order_by(FocusSession.completed_at.asc())
        .all()
    )

    sessions_in_period = [
        session for session in completed_sessions
        if _in_range(session.completed_at, selected_range.start_date, selected_range.end_date)
    ]
    sessions_previous = [
        session for session in completed_sessions
        if _in_range(session.completed_at, selected_range.previous_start, selected_range.previous_end)
    ]

    created_in_period = sum(
        1 for task in tasks
        if _in_range(task.created_at, selected_range.start_date, selected_range.end_date)
    )
    created_previous = sum(
        1 for task in tasks
        if _in_range(task.created_at, selected_range.previous_start, selected_range.previous_end)
    )
    completed_in_period = sum(
        1 for task in tasks
        if _in_range(task.completed_at, selected_range.start_date, selected_range.end_date)
    )
    completed_previous = sum(
        1 for task in tasks
        if _in_range(task.completed_at, selected_range.previous_start, selected_range.previous_end)
    )

    completed_total = sum(1 for task in tasks if task.status == COMPLETED_STATUS)
    open_tasks = [task for task in tasks if task.status != COMPLETED_STATUS]
    overdue_tasks = [
        task for task in open_tasks
        if task.deadline and task.deadline < date.today()
    ]
    blocked_tasks = [task for task in tasks if task.status == "Blocked"]
    recurring_tasks = [task for task in tasks if task.is_recurring]
    active_projects = [
        project for project in projects
        if project.status not in ("Completed", "Paused")
    ]

    focus_minutes = sum(session.actual_minutes or 0 for session in sessions_in_period)
    focus_previous = sum(session.actual_minutes or 0 for session in sessions_previous)
    average_session = round(focus_minutes / len(sessions_in_period)) if sessions_in_period else 0
    average_previous = round(focus_previous / len(sessions_previous)) if sessions_previous else 0
    overall_completion_rate = round((completed_total / len(tasks)) * 100) if tasks else 0

    buckets = _build_buckets(selected_range.start_date, selected_range.end_date)
    task_series = _task_bucket_series(tasks, buckets)
    focus_series = _focus_bucket_series(sessions_in_period, buckets)
    status_data = _status_distribution(tasks)
    priority_data = _priority_distribution(tasks)
    focus_by_project = _project_focus_data(sessions_in_period)
    project_rows = _project_rows(projects, tasks, sessions_in_period)

    general_tasks = sum(1 for task in tasks if task.project_id is None)
    project_tasks = len(tasks) - general_tasks
    recurring_completed = sum(1 for task in recurring_tasks if task.status == COMPLETED_STATUS)
    recurring_rate = round((recurring_completed / len(recurring_tasks)) * 100) if recurring_tasks else 0

    comparisons = {
        "completed": _percent_change(completed_in_period, completed_previous),
        "focus": _percent_change(focus_minutes, focus_previous),
        "created": _percent_change(created_in_period, created_previous),
        "average_session": _percent_change(average_session, average_previous),
    }

    return {
        "range": selected_range,
        "summary": {
            "completed_in_period": completed_in_period,
            "created_in_period": created_in_period,
            "completion_rate": overall_completion_rate,
            "focus_minutes": focus_minutes,
            "focus_label": _format_minutes(focus_minutes),
            "overdue_tasks": len(overdue_tasks),
            "active_projects": len(active_projects),
            "average_session": average_session,
            "average_session_label": _format_minutes(average_session),
            "open_tasks": len(open_tasks),
            "blocked_tasks": len(blocked_tasks),
            "recurring_tasks": len(recurring_tasks),
            "recurring_completion_rate": recurring_rate,
            "focus_sessions": len(sessions_in_period),
            "total_tasks": len(tasks),
        },
        "comparisons": comparisons,
        "task_series": task_series,
        "focus_series": focus_series,
        "status_data": status_data,
        "priority_data": priority_data,
        "scope_data": {
            "general": general_tasks,
            "project": project_tasks,
        },
        "focus_by_project": focus_by_project,
        "projects": project_rows,
        "insights": _build_insights(
            completed_in_period=completed_in_period,
            completed_previous=completed_previous,
            focus_minutes=focus_minutes,
            focus_previous=focus_previous,
            overdue_count=len(overdue_tasks),
            blocked_count=len(blocked_tasks),
            focus_by_project=focus_by_project,
            focus_series=focus_series,
            created_in_period=created_in_period,
        ),
        "generated_at": datetime.now(),
    }


def get_monthly_summary(user_id: int, year: int, month: int) -> dict:
    start_date = date(year, month, 1)
    end_date = date(year, month, monthrange(year, month)[1])
    data = get_analytics_dashboard(
        user_id=user_id,
        period="custom",
        start_value=start_date.isoformat(),
        end_value=end_date.isoformat(),
    )
    data["month_key"] = start_date.strftime("%Y-%m")
    data["month_label"] = start_date.strftime("%B %Y")
    return data


def previous_calendar_month(today: date | None = None) -> tuple[int, int]:
    today = today or date.today()
    previous_day = today.replace(day=1) - timedelta(days=1)
    return previous_day.year, previous_day.month


def task_export_rows(user_id: int) -> list[dict]:
    tasks = (
        Task.query
        .filter_by(user_id=user_id)
        .order_by(Task.created_at.desc())
        .all()
    )

    return [
        {
            "task_id": task.id,
            "title": task.title,
            "scope": task.project.title if task.project else "General Workspace",
            "status": task.status,
            "importance": task.importance,
            "difficulty": task.difficulty,
            "module": task.module or "",
            "deadline": task.deadline.isoformat() if task.deadline else "",
            "created_at": task.created_at.isoformat(sep=" ", timespec="minutes") if task.created_at else "",
            "completed_at": task.completed_at.isoformat(sep=" ", timespec="minutes") if task.completed_at else "",
            "is_recurring": "Yes" if task.is_recurring else "No",
            "recurrence_type": task.recurrence_type or "none",
        }
        for task in tasks
    ]


def focus_export_rows(user_id: int) -> list[dict]:
    sessions = (
        FocusSession.query
        .filter_by(user_id=user_id)
        .order_by(FocusSession.created_at.desc())
        .all()
    )

    return [
        {
            "session_id": session.id,
            "title": session.title,
            "task": session.task.title if session.task else "",
            "project": session.task.project.title if session.task and session.task.project else "General Workspace",
            "goal": session.goal or "",
            "planned_minutes": session.planned_minutes or 0,
            "actual_minutes": session.actual_minutes or 0,
            "status": session.status,
            "distractions": session.distraction_count or 0,
            "focus_rating": session.focus_rating or "",
            "goal_result": session.goal_result or "",
            "completed_at": session.completed_at.isoformat(sep=" ", timespec="minutes") if session.completed_at else "",
        }
        for session in sessions
    ]

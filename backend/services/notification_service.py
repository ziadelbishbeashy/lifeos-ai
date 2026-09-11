from datetime import date, datetime, time, timedelta

from database import db
from models import (
    EmailNotificationLog,
    NotificationPreference,
    Project,
    Task,
    User,
)
from services.email_service import send_email
from services.analytics_service import get_monthly_summary, previous_calendar_month


DEFAULT_APP_NAME = "LifeOS AI"


# =========================================================
# Core helpers
# =========================================================

def _today():
    return date.today()


def _now():
    return datetime.now()


def _task_scope(task):
    if task.project_id and task.project:
        return task.project.title

    return "General Workspace"


def _task_line(task):
    deadline = task.deadline.strftime("%Y-%m-%d") if task.deadline else "No deadline"

    return (
        f"- {task.title} | Scope: {_task_scope(task)} | "
        f"Priority: {task.importance} | Status: {task.status} | Due: {deadline}"
    )


def _safe_time_value(value, fallback):
    if isinstance(value, time):
        return value

    return fallback


def _is_time_reached(target_time):
    return _now().time() >= target_time


def _is_in_quiet_hours(preferences):
    start = preferences.quiet_hours_start
    end = preferences.quiet_hours_end

    if not start or not end:
        return False

    current_time = _now().time()

    if start < end:
        return start <= current_time < end

    return current_time >= start or current_time < end


def get_or_create_notification_preferences(user):
    preferences = user.notification_preferences

    if preferences:
        return preferences

    preferences = NotificationPreference(user_id=user.id)
    db.session.add(preferences)
    db.session.commit()

    return preferences


def log_exists(unique_key):
    return (
        EmailNotificationLog.query
        .filter_by(unique_key=unique_key)
        .first()
        is not None
    )


def create_log(
    user_id,
    notification_type,
    sent_to,
    unique_key,
    task_id=None,
    project_id=None,
    subject=None,
    status="sent",
    error_message=None,
):
    log = EmailNotificationLog(
        user_id=user_id,
        task_id=task_id,
        project_id=project_id,
        notification_type=notification_type,
        sent_to=sent_to,
        subject=subject,
        status=status,
        error_message=error_message,
        unique_key=unique_key,
    )

    db.session.add(log)
    db.session.commit()

    return log


def _email_shell(title, subtitle, sections):
    """Return a branded HTML email body."""

    section_html = []

    for heading, lines in sections:
        if not lines:
            continue

        line_items = "".join(
            f"<li>{line}</li>"
            for line in lines
        )

        section_html.append(
            f"""
            <div class="section">
                <h3>{heading}</h3>
                <ul>{line_items}</ul>
            </div>
            """
        )

    return f"""
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                margin: 0;
                padding: 0;
                background: #f4f7fb;
                color: #101828;
                font-family: Arial, Helvetica, sans-serif;
            }}
            .wrapper {{
                max-width: 680px;
                margin: 0 auto;
                padding: 28px 16px;
            }}
            .card {{
                background: #ffffff;
                border-radius: 20px;
                overflow: hidden;
                border: 1px solid #e5e7eb;
                box-shadow: 0 18px 45px rgba(15, 23, 42, 0.08);
            }}
            .header {{
                padding: 26px;
                background: linear-gradient(135deg, #5b5ff0, #8b5cf6);
                color: white;
            }}
            .header span {{
                display: inline-block;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 1.5px;
                opacity: .86;
                margin-bottom: 8px;
            }}
            .header h1 {{
                margin: 0;
                font-size: 26px;
            }}
            .header p {{
                margin: 8px 0 0;
                opacity: .92;
                line-height: 1.6;
            }}
            .content {{
                padding: 26px;
            }}
            .section {{
                border: 1px solid #edf0f5;
                border-radius: 16px;
                padding: 18px;
                margin-bottom: 16px;
                background: #fbfcff;
            }}
            .section h3 {{
                margin: 0 0 12px;
                font-size: 17px;
                color: #111827;
            }}
            ul {{
                margin: 0;
                padding-left: 18px;
            }}
            li {{
                margin: 8px 0;
                line-height: 1.55;
            }}
            .footer {{
                padding: 20px 26px 26px;
                color: #667085;
                font-size: 13px;
                line-height: 1.6;
            }}
        </style>
    </head>
    <body>
        <div class="wrapper">
            <div class="card">
                <div class="header">
                    <span>{DEFAULT_APP_NAME}</span>
                    <h1>{title}</h1>
                    <p>{subtitle}</p>
                </div>
                <div class="content">
                    {''.join(section_html)}
                </div>
                <div class="footer">
                    Open LifeOS AI to update your workspace, complete tasks, or change notification settings.
                </div>
            </div>
        </div>
    </body>
    </html>
    """


# =========================================================
# Email actions
# =========================================================

def send_test_email(user):
    subject = "LifeOS AI test email"

    body = (
        f"Hi {user.name},\n\n"
        "This is a test email from LifeOS AI Phase 5.1.\n\n"
        "If you received this, your email configuration is working.\n\n"
        "LifeOS AI"
    )

    html_body = _email_shell(
        "Email connection is working",
        "Your LifeOS notification sender is configured correctly.",
        [
            (
                "Status",
                [
                    "SMTP connection succeeded.",
                    "LifeOS can now send reminders, daily checkups, and analytics emails.",
                ],
            )
        ],
    )

    send_email(user.email, subject, body, html_body=html_body)

    unique_key = f"test_email_{user.id}_{_today().isoformat()}"

    if not log_exists(unique_key):
        create_log(
            user_id=user.id,
            notification_type="test_email",
            sent_to=user.email,
            unique_key=unique_key,
            subject=subject,
        )

    return True


def get_user_open_tasks(user_id):
    return (
        Task.query
        .filter(
            Task.user_id == user_id,
            Task.status != "Completed",
        )
        .order_by(Task.deadline.asc(), Task.created_at.desc())
        .all()
    )


def send_daily_summary_email(user, force=False):
    preferences = get_or_create_notification_preferences(user)

    if not force:
        if not preferences.email_enabled or not preferences.daily_checkup_enabled:
            return False

        if _is_in_quiet_hours(preferences):
            return False

        target_time = _safe_time_value(preferences.daily_checkup_time, time(8, 0))

        if not _is_time_reached(target_time):
            return False

    today = _today()
    soon_limit = today + timedelta(days=7)

    open_tasks = get_user_open_tasks(user.id)

    overdue_tasks = [
        task for task in open_tasks
        if task.deadline and task.deadline < today
    ]

    due_today_tasks = [
        task for task in open_tasks
        if task.deadline == today
    ]

    due_soon_tasks = [
        task for task in open_tasks
        if task.deadline and today < task.deadline <= soon_limit
    ]

    unique_key = f"daily_summary_{user.id}_{today.isoformat()}"

    if log_exists(unique_key):
        return False

    subject = f"LifeOS Daily Checkup - {today.strftime('%Y-%m-%d')}"

    body_parts = [
        f"Hi {user.name},",
        "",
        "Here is your LifeOS daily workspace checkup.",
        "",
        f"Open tasks: {len(open_tasks)}",
        f"Overdue tasks: {len(overdue_tasks)}",
        f"Due today: {len(due_today_tasks)}",
        f"Due in the next 7 days: {len(due_soon_tasks)}",
        "",
    ]

    if overdue_tasks:
        body_parts.append("Overdue tasks:")
        body_parts.extend(_task_line(task) for task in overdue_tasks[:10])
        body_parts.append("")

    if due_today_tasks:
        body_parts.append("Due today:")
        body_parts.extend(_task_line(task) for task in due_today_tasks[:10])
        body_parts.append("")

    if due_soon_tasks:
        body_parts.append("Upcoming tasks:")
        body_parts.extend(_task_line(task) for task in due_soon_tasks[:10])
        body_parts.append("")

    if not open_tasks:
        body_parts.append("No open tasks. Your workspace is clear.")
        body_parts.append("")

    body_parts.extend([
        "Open LifeOS AI to update your workspace.",
        "",
        DEFAULT_APP_NAME,
    ])

    html_body = _email_shell(
        "Daily Checkup",
        f"Good morning {user.name}. Here is your workspace snapshot for today.",
        [
            (
                "Quick Stats",
                [
                    f"Open tasks: {len(open_tasks)}",
                    f"Overdue tasks: {len(overdue_tasks)}",
                    f"Due today: {len(due_today_tasks)}",
                    f"Upcoming this week: {len(due_soon_tasks)}",
                ],
            ),
            ("Overdue Tasks", [_task_line(task) for task in overdue_tasks[:10]]),
            ("Due Today", [_task_line(task) for task in due_today_tasks[:10]]),
            ("Upcoming", [_task_line(task) for task in due_soon_tasks[:10]]),
        ],
    )

    send_email(user.email, subject, "\n".join(body_parts), html_body=html_body)

    create_log(
        user_id=user.id,
        notification_type="daily_summary",
        sent_to=user.email,
        unique_key=unique_key,
        subject=subject,
    )

    return True


def send_weekly_summary_email(user, force=False):
    preferences = get_or_create_notification_preferences(user)

    if not force:
        if not preferences.email_enabled or not preferences.weekly_summary_enabled:
            return False

        if _is_in_quiet_hours(preferences):
            return False

        if _now().weekday() != preferences.weekly_summary_day:
            return False

        target_time = _safe_time_value(preferences.weekly_summary_time, time(18, 0))

        if not _is_time_reached(target_time):
            return False

    today = _today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    tasks = (
        Task.query
        .filter(Task.user_id == user.id)
        .all()
    )

    completed = [task for task in tasks if task.status == "Completed"]
    open_tasks = [task for task in tasks if task.status != "Completed"]
    overdue = [task for task in open_tasks if task.deadline and task.deadline < today]
    due_this_week = [
        task for task in open_tasks
        if task.deadline and week_start <= task.deadline <= week_end
    ]

    unique_key = f"weekly_summary_{user.id}_{week_start.isoformat()}"

    if log_exists(unique_key):
        return False

    subject = f"LifeOS Weekly Summary - Week of {week_start.strftime('%Y-%m-%d')}"

    lines = [
        f"Hi {user.name},",
        "",
        "Here is your LifeOS weekly productivity summary.",
        "",
        f"Completed tasks: {len(completed)}",
        f"Open tasks: {len(open_tasks)}",
        f"Overdue tasks: {len(overdue)}",
        f"Due this week: {len(due_this_week)}",
        "",
        DEFAULT_APP_NAME,
    ]

    html_body = _email_shell(
        "Weekly Summary",
        "A quick review of your workspace progress and risks.",
        [
            (
                "Weekly Stats",
                [
                    f"Completed tasks: {len(completed)}",
                    f"Open tasks: {len(open_tasks)}",
                    f"Overdue tasks: {len(overdue)}",
                    f"Due this week: {len(due_this_week)}",
                ],
            ),
            ("Tasks Due This Week", [_task_line(task) for task in due_this_week[:12]]),
            ("Overdue Work", [_task_line(task) for task in overdue[:12]]),
        ],
    )

    send_email(user.email, subject, "\n".join(lines), html_body=html_body)

    create_log(
        user_id=user.id,
        notification_type="weekly_summary",
        sent_to=user.email,
        unique_key=unique_key,
        subject=subject,
    )

    return True


def send_monthly_analytics_email(user, force=False):
    preferences = get_or_create_notification_preferences(user)

    if not force:
        if not preferences.email_enabled or not preferences.monthly_analytics_enabled:
            return False

        if _is_in_quiet_hours(preferences):
            return False

        report_day = max(1, min(28, preferences.monthly_report_day or 1))

        if _today().day != report_day:
            return False

        target_time = _safe_time_value(preferences.monthly_report_time, time(8, 0))

        if not _is_time_reached(target_time):
            return False

    report_year, report_month = previous_calendar_month(_today())
    analytics = get_monthly_summary(user.id, report_year, report_month)
    summary = analytics["summary"]
    month_key = analytics["month_key"]
    month_label = analytics["month_label"]

    unique_key = f"monthly_analytics_{user.id}_{month_key}"

    if log_exists(unique_key):
        return False

    most_focused_project = (
        analytics["focus_by_project"][0]["name"]
        if analytics["focus_by_project"]
        else "No focus activity recorded"
    )

    open_overdue = (
        Task.query
        .filter(
            Task.user_id == user.id,
            Task.status != "Completed",
            Task.deadline.isnot(None),
            Task.deadline < _today(),
        )
        .order_by(Task.deadline.asc())
        .limit(8)
        .all()
    )

    subject = f"LifeOS Monthly Analytics - {month_label}"

    text_lines = [
        f"Hi {user.name},",
        "",
        f"Here is your LifeOS productivity report for {month_label}.",
        "",
        f"Tasks completed: {summary['completed_in_period']}",
        f"Tasks created: {summary['created_in_period']}",
        f"Overall completion rate: {summary['completion_rate']}%",
        f"Focus time: {summary['focus_label']}",
        f"Focus sessions: {summary['focus_sessions']}",
        f"Average focus session: {summary['average_session_label']}",
        f"Current overdue tasks: {summary['overdue_tasks']}",
        f"Active projects: {summary['active_projects']}",
        f"Most focused area: {most_focused_project}",
        "",
        DEFAULT_APP_NAME,
    ]

    html_body = _email_shell(
        "Monthly Analytics",
        f"Your LifeOS productivity report for {month_label}.",
        [
            (
                "Task Activity",
                [
                    f"Tasks completed: {summary['completed_in_period']}",
                    f"Tasks created: {summary['created_in_period']}",
                    f"Overall completion rate: {summary['completion_rate']}%",
                    f"Current overdue tasks: {summary['overdue_tasks']}",
                ],
            ),
            (
                "Focus Activity",
                [
                    f"Focused time: {summary['focus_label']}",
                    f"Sessions completed: {summary['focus_sessions']}",
                    f"Average session: {summary['average_session_label']}",
                    f"Most focused area: {most_focused_project}",
                ],
            ),
            (
                "Project Activity",
                [
                    f"Active projects: {summary['active_projects']}",
                    f"Recurring task completion: {summary['recurring_completion_rate']}%",
                ],
            ),
            ("Current Overdue Work", [_task_line(task) for task in open_overdue]),
        ],
    )

    send_email(user.email, subject, "\n".join(text_lines), html_body=html_body)

    create_log(
        user_id=user.id,
        notification_type="monthly_analytics",
        sent_to=user.email,
        unique_key=unique_key,
        subject=subject,
    )

    return True


def send_custom_task_reminders(user):
    preferences = get_or_create_notification_preferences(user)

    if (
        not preferences.email_enabled
        or not preferences.custom_task_reminders_enabled
        or _is_in_quiet_hours(preferences)
    ):
        return 0

    now = _now()

    reminder_tasks = (
        Task.query
        .filter(
            Task.user_id == user.id,
            Task.status != "Completed",
            Task.reminder_enabled == True,
            Task.reminder_datetime.isnot(None),
            Task.reminder_datetime <= now,
        )
        .order_by(Task.reminder_datetime.asc())
        .all()
    )

    sent_count = 0

    for task in reminder_tasks:
        unique_key = (
            f"custom_task_reminder_{user.id}_{task.id}_"
            f"{task.reminder_datetime.strftime('%Y%m%d%H%M')}"
        )

        if log_exists(unique_key):
            continue

        subject = f"LifeOS Reminder: {task.title}"

        body = (
            f"Hi {user.name},\n\n"
            "This is your custom LifeOS task reminder.\n\n"
            f"Task: {task.title}\n"
            f"Scope: {_task_scope(task)}\n"
            f"Priority: {task.importance}\n"
            f"Status: {task.status}\n"
            f"Reminder time: {task.reminder_datetime.strftime('%Y-%m-%d %H:%M')}\n"
            f"Deadline: {task.deadline.strftime('%Y-%m-%d') if task.deadline else 'No deadline'}\n\n"
            "Open LifeOS AI to update or complete it.\n\n"
            "LifeOS AI"
        )

        html_body = _email_shell(
            "Task Reminder",
            "You asked LifeOS to remind you about this task.",
            [
                (
                    "Reminder Details",
                    [
                        f"Task: {task.title}",
                        f"Scope: {_task_scope(task)}",
                        f"Priority: {task.importance}",
                        f"Status: {task.status}",
                        f"Deadline: {task.deadline.strftime('%Y-%m-%d') if task.deadline else 'No deadline'}",
                    ],
                )
            ],
        )

        send_email(user.email, subject, body, html_body=html_body)

        task.last_reminder_sent_at = now

        create_log(
            user_id=user.id,
            task_id=task.id,
            notification_type="custom_task_reminder",
            sent_to=user.email,
            unique_key=unique_key,
            subject=subject,
        )

        sent_count += 1

    db.session.commit()

    return sent_count


def send_task_deadline_reminders(user):
    preferences = get_or_create_notification_preferences(user)

    if not preferences.email_enabled or not preferences.task_reminders_enabled:
        return 0

    if _is_in_quiet_hours(preferences):
        return 0

    today = _today()
    days_before = max(0, preferences.task_reminder_days_before or 1)
    reminder_day = today + timedelta(days=days_before)

    reminder_tasks = (
        Task.query
        .filter(
            Task.user_id == user.id,
            Task.status != "Completed",
            Task.deadline.isnot(None),
        )
        .order_by(Task.deadline.asc())
        .all()
    )

    sent_count = 0

    for task in reminder_tasks:
        notification_type = None
        subject = None
        intro = None

        if days_before > 0 and task.deadline == reminder_day:
            notification_type = f"task_due_in_{days_before}_days"
            subject = f"LifeOS Reminder: {task.title} is due in {days_before} day(s)"
            intro = f"This task is due in {days_before} day(s)."

        elif task.deadline == today:
            notification_type = "task_due_today"
            subject = f"LifeOS Reminder: {task.title} is due today"
            intro = "This task is due today."

        elif task.deadline < today and preferences.overdue_alerts_enabled:
            notification_type = "task_overdue"
            subject = f"LifeOS Alert: {task.title} is overdue"
            intro = "This task is overdue."

        if not notification_type:
            continue

        unique_key = (
            f"{notification_type}_{user.id}_{task.id}_{today.isoformat()}"
        )

        if log_exists(unique_key):
            continue

        body = (
            f"Hi {user.name},\n\n"
            f"{intro}\n\n"
            f"Task: {task.title}\n"
            f"Scope: {_task_scope(task)}\n"
            f"Priority: {task.importance}\n"
            f"Difficulty: {task.difficulty}\n"
            f"Status: {task.status}\n"
            f"Deadline: {task.deadline.strftime('%Y-%m-%d')}\n\n"
            "Open LifeOS AI to update or complete it.\n\n"
            "LifeOS AI"
        )

        html_body = _email_shell(
            "Deadline Reminder",
            intro,
            [
                (
                    "Task Details",
                    [
                        f"Task: {task.title}",
                        f"Scope: {_task_scope(task)}",
                        f"Priority: {task.importance}",
                        f"Difficulty: {task.difficulty}",
                        f"Status: {task.status}",
                        f"Deadline: {task.deadline.strftime('%Y-%m-%d')}",
                    ],
                )
            ],
        )

        send_email(user.email, subject, body, html_body=html_body)

        create_log(
            user_id=user.id,
            task_id=task.id,
            notification_type=notification_type,
            sent_to=user.email,
            unique_key=unique_key,
            subject=subject,
        )

        sent_count += 1

    return sent_count


def run_email_notification_check(user_id=None, include_automatic_summaries=True):
    users_query = User.query

    if user_id:
        users_query = users_query.filter_by(id=user_id)

    users = users_query.all()

    result = {
        "users_checked": len(users),
        "custom_reminders_sent": 0,
        "deadline_reminders_sent": 0,
        "daily_summaries_sent": 0,
        "weekly_summaries_sent": 0,
        "monthly_reports_sent": 0,
    }

    for user in users:
        preferences = get_or_create_notification_preferences(user)

        if not preferences.email_enabled:
            continue

        result["custom_reminders_sent"] += send_custom_task_reminders(user)
        result["deadline_reminders_sent"] += send_task_deadline_reminders(user)

        if include_automatic_summaries:
            if send_daily_summary_email(user):
                result["daily_summaries_sent"] += 1

            if send_weekly_summary_email(user):
                result["weekly_summaries_sent"] += 1

            if send_monthly_analytics_email(user):
                result["monthly_reports_sent"] += 1

    return result

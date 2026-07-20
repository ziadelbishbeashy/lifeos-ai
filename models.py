from datetime import datetime, time

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from database import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode(120), nullable=False)
    email = db.Column(db.Unicode(255), nullable=False, unique=True)
    password_hash = db.Column(db.Unicode(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    projects = db.relationship("Project", back_populates="owner", lazy=True)

    tasks = db.relationship(
        "Task",
        back_populates="owner",
        lazy=True,
        cascade="all, delete-orphan",
    )

    email_notifications = db.relationship(
        "EmailNotificationLog",
        back_populates="user",
        lazy=True,
        cascade="all, delete-orphan",
    )

    focus_sessions = db.relationship(
        "FocusSession",
        back_populates="user",
        lazy=True,
        cascade="all, delete-orphan",
    )

    focus_distractions = db.relationship(
        "FocusDistraction",
        back_populates="user",
        lazy=True,
        cascade="all, delete-orphan",
    )

    notification_preferences = db.relationship(
        "NotificationPreference",
        back_populates="user",
        uselist=False,
        lazy=True,
        cascade="all, delete-orphan",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email}>"


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    owner = db.relationship("User", back_populates="projects")

    title = db.Column(db.Unicode(150), nullable=False)
    description = db.Column(db.UnicodeText, nullable=True)
    project_type = db.Column(db.Unicode(100), nullable=True)
    goal = db.Column(db.UnicodeText, nullable=True)
    tech_stack = db.Column(db.Unicode(300), nullable=True)
    project_folder = db.Column(db.Unicode(500), nullable=True)
    github_link = db.Column(db.Unicode(500), nullable=True)
    demo_link = db.Column(db.Unicode(500), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    deadline = db.Column(db.Date, nullable=True)
    status = db.Column(db.Unicode(50), default="In Progress")
    priority = db.Column(db.Unicode(50), default="Medium")
    current_phase = db.Column(db.Unicode(100), nullable=True)
    progress = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    tasks = db.relationship(
        "Task",
        back_populates="project",
        lazy=True,
        cascade="all, delete-orphan",
    )
    notes = db.relationship(
        "Note",
        backref="project",
        lazy=True,
        cascade="all, delete-orphan",
    )
    documents = db.relationship(
        "Document",
        backref="project",
        lazy=True,
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Project {self.title}>"


class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)

    # Phase 5.0:
    # Every task belongs to the user workspace.
    # It may optionally also belong to a project.
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    owner = db.relationship("User", back_populates="tasks")

    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True, index=True)
    project = db.relationship("Project", back_populates="tasks")

    email_notifications = db.relationship(
        "EmailNotificationLog",
        back_populates="task",
        lazy=True,
        cascade="all, delete-orphan",
    )

    focus_sessions = db.relationship(
        "FocusSession",
        back_populates="task",
        lazy=True,
    )

    title = db.Column(db.Unicode(200), nullable=False)
    description = db.Column(db.UnicodeText, nullable=True)
    module = db.Column(db.Unicode(100), nullable=True)
    importance = db.Column(db.Unicode(50), default="Medium")
    difficulty = db.Column(db.Unicode(50), default="Medium")
    deadline = db.Column(db.Date, nullable=True)
    status = db.Column(db.Unicode(50), default="Pending")
    priority_score = db.Column(db.Float, default=0)
    reason = db.Column(db.UnicodeText, nullable=True)

    # Phase 5.1 Professional Notifications:
    # Custom user-controlled reminder per task.
    reminder_enabled = db.Column(db.Boolean, nullable=False, default=False)
    reminder_type = db.Column(db.Unicode(50), nullable=False, default="none")
    reminder_datetime = db.Column(db.DateTime, nullable=True)
    last_reminder_sent_at = db.Column(db.DateTime, nullable=True)

    # Phase 5.2 Recurring Tasks
    is_recurring = db.Column(db.Boolean, nullable=False, default=False)
    recurrence_type = db.Column(db.Unicode(30), nullable=False, default="none")
    recurrence_interval = db.Column(db.Integer, nullable=False, default=1)
    recurrence_end_date = db.Column(db.Date, nullable=True)
    recurrence_parent_id = db.Column(
        db.Integer,
        db.ForeignKey("tasks.id"),
        nullable=True,
        index=True,
    )
    recurrence_series_id = db.Column(db.Integer, nullable=True, index=True)
    next_occurrence_date = db.Column(db.Date, nullable=True)
    last_generated_at = db.Column(db.DateTime, nullable=True)

    recurrence_parent = db.relationship(
        "Task",
        remote_side=[id],
        foreign_keys=[recurrence_parent_id],
        backref=db.backref("generated_occurrences", lazy=True),
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True, index=True)

    @property
    def is_general(self):
        return self.project_id is None

    @property
    def scope_label(self):
        return "General Workspace" if self.is_general else "Project Task"

    def __repr__(self):
        return f"<Task {self.title}>"


class FocusSession(db.Model):
    __tablename__ = "focus_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=True, index=True)

    title = db.Column(db.Unicode(200), nullable=False)
    goal = db.Column(db.UnicodeText, nullable=True)
    planned_minutes = db.Column(db.Integer, nullable=False, default=25)
    actual_minutes = db.Column(db.Integer, nullable=False, default=0)
    elapsed_seconds = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.Unicode(30), nullable=False, default="running", index=True)
    distraction_count = db.Column(db.Integer, nullable=False, default=0)
    goal_result = db.Column(db.Unicode(20), nullable=True)
    focus_rating = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.UnicodeText, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", back_populates="focus_sessions")
    task = db.relationship("Task", back_populates="focus_sessions")
    distractions = db.relationship(
        "FocusDistraction",
        back_populates="session",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="FocusDistraction.captured_at.asc()",
    )

    def __repr__(self):
        return f"<FocusSession {self.title}>"


class FocusDistraction(db.Model):
    __tablename__ = "focus_distractions"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("focus_sessions.id"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    content = db.Column(db.Unicode(500), nullable=False)
    captured_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    converted_task_id = db.Column(
        db.Integer,
        db.ForeignKey("tasks.id"),
        nullable=True,
        index=True,
    )

    session = db.relationship("FocusSession", back_populates="distractions")
    user = db.relationship("User", back_populates="focus_distractions")
    converted_task = db.relationship("Task", foreign_keys=[converted_task_id])

    def __repr__(self):
        return f"<FocusDistraction {self.content[:40]}>"


class NotificationPreference(db.Model):
    __tablename__ = "notification_preferences"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Master switch
    email_enabled = db.Column(db.Boolean, nullable=False, default=True)

    # Email categories
    task_reminders_enabled = db.Column(db.Boolean, nullable=False, default=True)
    custom_task_reminders_enabled = db.Column(db.Boolean, nullable=False, default=True)
    overdue_alerts_enabled = db.Column(db.Boolean, nullable=False, default=True)
    project_deadline_alerts_enabled = db.Column(db.Boolean, nullable=False, default=True)
    project_risk_alerts_enabled = db.Column(db.Boolean, nullable=False, default=True)
    daily_checkup_enabled = db.Column(db.Boolean, nullable=False, default=False)
    weekly_summary_enabled = db.Column(db.Boolean, nullable=False, default=False)
    monthly_analytics_enabled = db.Column(db.Boolean, nullable=False, default=False)

    # Timing preferences
    task_reminder_days_before = db.Column(db.Integer, nullable=False, default=1)
    project_reminder_days_before = db.Column(db.Integer, nullable=False, default=3)
    daily_checkup_time = db.Column(db.Time, nullable=False, default=lambda: time(8, 0))
    weekly_summary_day = db.Column(db.Integer, nullable=False, default=6)  # Monday=0, Sunday=6
    weekly_summary_time = db.Column(db.Time, nullable=False, default=lambda: time(18, 0))
    monthly_report_day = db.Column(db.Integer, nullable=False, default=1)
    monthly_report_time = db.Column(db.Time, nullable=False, default=lambda: time(8, 0))
    quiet_hours_start = db.Column(db.Time, nullable=True)
    quiet_hours_end = db.Column(db.Time, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    user = db.relationship("User", back_populates="notification_preferences")

    def __repr__(self):
        return f"<NotificationPreference user_id={self.user_id}>"


class EmailNotificationLog(db.Model):
    __tablename__ = "email_notification_logs"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    task_id = db.Column(
        db.Integer,
        db.ForeignKey("tasks.id"),
        nullable=True,
        index=True,
    )

    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id"),
        nullable=True,
        index=True,
    )

    notification_type = db.Column(db.Unicode(80), nullable=False)
    sent_to = db.Column(db.Unicode(255), nullable=False)
    subject = db.Column(db.Unicode(255), nullable=True)
    status = db.Column(db.Unicode(50), nullable=False, default="sent")
    error_message = db.Column(db.UnicodeText, nullable=True)

    # unique_key prevents duplicate reminders for the same user/task/day.
    unique_key = db.Column(db.Unicode(255), nullable=False, unique=True, index=True)

    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="email_notifications")
    task = db.relationship("Task", back_populates="email_notifications")
    project = db.relationship("Project")

    def __repr__(self):
        return f"<EmailNotificationLog {self.notification_type}>"


class Note(db.Model):
    __tablename__ = "notes"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    title = db.Column(db.Unicode(150), nullable=False)
    content = db.Column(db.UnicodeText, nullable=False)
    detected_modules = db.Column(db.UnicodeText, nullable=True)
    extracted_tasks = db.Column(db.UnicodeText, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Note {self.title}>"


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    filename = db.Column(db.Unicode(255), nullable=False)
    file_path = db.Column(db.Unicode(500), nullable=False)
    extracted_text = db.Column(db.UnicodeText, nullable=True)
    summary = db.Column(db.UnicodeText, nullable=True)
    detected_modules = db.Column(db.UnicodeText, nullable=True)
    extracted_tasks = db.Column(db.UnicodeText, nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Document {self.filename}>"

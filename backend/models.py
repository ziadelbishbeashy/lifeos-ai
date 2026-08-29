import json
from datetime import datetime, time

from sqlalchemy import event, select

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from database import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode(120), nullable=False)
    email = db.Column(db.Unicode(255), nullable=False, unique=True)
    password_hash = db.Column(db.Unicode(255), nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    projects = db.relationship(
        "Project",
        back_populates="owner",
        lazy=True,
    )

    tasks = db.relationship(
        "Task",
        back_populates="owner",
        lazy=True,
        cascade="all, delete-orphan",
    )

    notes = db.relationship(
        "Note",
        back_populates="owner",
        lazy=True,
        cascade="all, delete-orphan",
    )

    note_ai_analyses = db.relationship(
        "NoteAIAnalysis",
        back_populates="user",
        lazy=True,
    )
    document_ai_analyses = db.relationship(
    "DocumentAIAnalysis",
    back_populates="user",
    lazy=True,
    )

    document_questions = db.relationship(
    "DocumentQuestion",
    back_populates="user",
    lazy=True,
    )
    project_questions = db.relationship(
    "ProjectQuestion",
    back_populates="user",
    lazy=True,
    cascade="all, delete-orphan",
    )
    document_comparisons = db.relationship(
        "DocumentComparison",
        back_populates="user",
        lazy=True,
        cascade="all, delete-orphan",
    )
    document_version_families = db.relationship(
        "DocumentVersionFamily",
        back_populates="user",
        lazy=True,
    )
    document_task_suggestions = db.relationship(
    "DocumentTaskSuggestion",
    back_populates="user",
    lazy=True,
    )

    document_chunks = db.relationship(
    "DocumentChunk",
    back_populates="user",
    lazy=True,
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
    note_ai_questions = db.relationship(
        "NoteAIQuestion",
        back_populates="user",
        lazy=True,
        foreign_keys="NoteAIQuestion.user_id",
    )

    documents = db.relationship(
        "Document",
        back_populates="owner",
        lazy=True,
        foreign_keys="Document.user_id",
    )

    modules = db.relationship(
        "LearningModule",
        back_populates="owner",
        lazy=True,
        cascade="all, delete-orphan",
    )

    module_questions = db.relationship(
        "ModuleQuestion",
        back_populates="user",
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

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    owner = db.relationship(
        "User",
        back_populates="projects",
    )

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
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )
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

    # A note may be linked to a project, but the user still owns it.
    # Removing the project link must not delete the note.
    notes = db.relationship(
        "Note",
        back_populates="project",
        lazy=True,
    )

    documents = db.relationship(
        "Document",
        backref="project",
        lazy=True,
        cascade="all, delete-orphan",
    )

    document_version_families = db.relationship(
        "DocumentVersionFamily",
        back_populates="project",
        lazy=True,
        cascade="all, delete-orphan",
    )

    project_questions = db.relationship(
        "ProjectQuestion",
        back_populates="project",
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
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    owner = db.relationship(
        "User",
        back_populates="tasks",
    )

    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id"),
        nullable=True,
        index=True,
    )
    project = db.relationship(
        "Project",
        back_populates="tasks",
    )

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
    tags = db.Column(db.Unicode(500), nullable=True)
    importance = db.Column(db.Unicode(50), default="Medium")
    difficulty = db.Column(db.Unicode(50), default="Medium")
    deadline = db.Column(db.Date, nullable=True)
    status = db.Column(db.Unicode(50), default="Pending")
    priority_score = db.Column(db.Float, default=0)
    reason = db.Column(db.UnicodeText, nullable=True)

    # Phase 5.1 Professional Notifications:
    # Custom user-controlled reminder per task.
    reminder_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )
    reminder_type = db.Column(
        db.Unicode(50),
        nullable=False,
        default="none",
    )
    reminder_datetime = db.Column(db.DateTime, nullable=True)
    last_reminder_sent_at = db.Column(db.DateTime, nullable=True)

    # Phase 5.2 Recurring Tasks
    is_recurring = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )
    recurrence_type = db.Column(
        db.Unicode(30),
        nullable=False,
        default="none",
    )
    recurrence_interval = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )
    recurrence_end_date = db.Column(db.Date, nullable=True)

    recurrence_parent_id = db.Column(
        db.Integer,
        db.ForeignKey("tasks.id"),
        nullable=True,
        index=True,
    )
    recurrence_series_id = db.Column(
        db.Integer,
        nullable=True,
        index=True,
    )
    next_occurrence_date = db.Column(db.Date, nullable=True)
    last_generated_at = db.Column(db.DateTime, nullable=True)

    recurrence_parent = db.relationship(
        "Task",
        remote_side=[id],
        foreign_keys=[recurrence_parent_id],
        backref=db.backref(
            "generated_occurrences",
            lazy=True,
        ),
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )
    completed_at = db.Column(
        db.DateTime,
        nullable=True,
        index=True,
    )

    @property
    def is_general(self):
        return self.project_id is None

    @property
    def scope_label(self):
        return "General Workspace" if self.is_general else "Project Task"

    @property
    def tags_list(self) -> list[str]:
        """Return normalized comma-separated task tags."""

        if not self.tags:
            return []

        return [
            item.strip()
            for item in self.tags.split(",")
            if item.strip()
        ]

    def __repr__(self):
        return f"<Task {self.title}>"


class FocusSession(db.Model):
    __tablename__ = "focus_sessions"

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

    title = db.Column(db.Unicode(200), nullable=False)
    goal = db.Column(db.UnicodeText, nullable=True)
    planned_minutes = db.Column(
        db.Integer,
        nullable=False,
        default=25,
    )
    actual_minutes = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )
    elapsed_seconds = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )
    status = db.Column(
        db.Unicode(30),
        nullable=False,
        default="running",
        index=True,
    )
    distraction_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )
    goal_result = db.Column(db.Unicode(20), nullable=True)
    focus_rating = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.UnicodeText, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    user = db.relationship(
        "User",
        back_populates="focus_sessions",
    )
    task = db.relationship(
        "Task",
        back_populates="focus_sessions",
    )
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

    content = db.Column(
        db.Unicode(500),
        nullable=False,
    )
    captured_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    converted_task_id = db.Column(
        db.Integer,
        db.ForeignKey("tasks.id"),
        nullable=True,
        index=True,
    )

    session = db.relationship(
        "FocusSession",
        back_populates="distractions",
    )
    user = db.relationship(
        "User",
        back_populates="focus_distractions",
    )
    converted_task = db.relationship(
        "Task",
        foreign_keys=[converted_task_id],
    )

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
    email_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    # Email categories
    task_reminders_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )
    custom_task_reminders_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )
    overdue_alerts_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )
    project_deadline_alerts_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )
    project_risk_alerts_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )
    daily_checkup_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )
    weekly_summary_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )
    monthly_analytics_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    # Timing preferences
    task_reminder_days_before = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )
    project_reminder_days_before = db.Column(
        db.Integer,
        nullable=False,
        default=3,
    )
    daily_checkup_time = db.Column(
        db.Time,
        nullable=False,
        default=lambda: time(8, 0),
    )
    weekly_summary_day = db.Column(
        db.Integer,
        nullable=False,
        default=6,
    )  # Monday=0, Sunday=6
    weekly_summary_time = db.Column(
        db.Time,
        nullable=False,
        default=lambda: time(18, 0),
    )
    monthly_report_day = db.Column(
        db.Integer,
        nullable=False,
        default=1,
    )
    monthly_report_time = db.Column(
        db.Time,
        nullable=False,
        default=lambda: time(8, 0),
    )
    quiet_hours_start = db.Column(db.Time, nullable=True)
    quiet_hours_end = db.Column(db.Time, nullable=True)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    user = db.relationship(
        "User",
        back_populates="notification_preferences",
    )

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

    notification_type = db.Column(
        db.Unicode(80),
        nullable=False,
    )
    sent_to = db.Column(
        db.Unicode(255),
        nullable=False,
    )
    subject = db.Column(db.Unicode(255), nullable=True)
    status = db.Column(
        db.Unicode(50),
        nullable=False,
        default="sent",
    )
    error_message = db.Column(db.UnicodeText, nullable=True)

    # Prevent duplicate reminders for the same event.
    unique_key = db.Column(
        db.Unicode(255),
        nullable=False,
        unique=True,
        index=True,
    )

    sent_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    user = db.relationship(
        "User",
        back_populates="email_notifications",
    )
    task = db.relationship(
        "Task",
        back_populates="email_notifications",
    )
    project = db.relationship("Project")





    def __repr__(self):
        return f"<EmailNotificationLog {self.notification_type}>"


class Note(db.Model):
    __tablename__ = "notes"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id"),
        nullable=True,
        index=True,
    )

    title = db.Column(
        db.Unicode(255),
        nullable=False,
    )
    content = db.Column(
        db.UnicodeText,
        nullable=False,
    )
    note_type = db.Column(
        db.Unicode(50),
        nullable=False,
        default="Quick Note",
    )
    is_pinned = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    owner = db.relationship(
        "User",
        back_populates="notes",
    )
    project = db.relationship(
        "Project",
        back_populates="notes",
    )

    analyses = db.relationship(
        "NoteAIAnalysis",
        back_populates="note",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="NoteAIAnalysis.created_at.desc()",
    )

    task_suggestions = db.relationship(
        "AITaskSuggestion",
        back_populates="note",
        lazy=True,
    )

    ai_questions = db.relationship(
        "NoteAIQuestion",
        back_populates="note",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="NoteAIQuestion.created_at.desc()",
        foreign_keys="NoteAIQuestion.note_id",
    )

    @property
    def is_general(self):
        return self.project_id is None

    @property
    def type_label(self):
        return self.note_type or "Quick Note"

    def __repr__(self):
        return f"<Note {self.title}>"


class NoteAIAnalysis(db.Model):
    __tablename__ = "note_ai_analyses"

    id = db.Column(db.Integer, primary_key=True)

    note_id = db.Column(
        db.Integer,
        db.ForeignKey("notes.id"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    provider = db.Column(
        db.Unicode(30),
        nullable=False,
    )
    model = db.Column(
        db.Unicode(100),
        nullable=False,
    )
    status = db.Column(
        db.Unicode(20),
        nullable=False,
        default="Completed",
    )

    summary = db.Column(db.UnicodeText, nullable=True)
    tags_json = db.Column(db.UnicodeText, nullable=True)
    deadlines_json = db.Column(db.UnicodeText, nullable=True)
    decisions_json = db.Column(db.UnicodeText, nullable=True)
    questions_json = db.Column(db.UnicodeText, nullable=True)
    insights_json = db.Column(db.UnicodeText, nullable=True)
    error_message = db.Column(db.UnicodeText, nullable=True)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    note = db.relationship(
        "Note",
        back_populates="analyses",
    )
    user = db.relationship(
        "User",
        back_populates="note_ai_analyses",
    )

    task_suggestions = db.relationship(
        "AITaskSuggestion",
        back_populates="analysis",
        lazy=True,
        cascade="all, delete-orphan",
    )

    questions_history = db.relationship(
        "NoteAIQuestion",
        back_populates="analysis",
        lazy=True,
        foreign_keys="NoteAIQuestion.analysis_id",
    )


    @property
    def tags(self):
        return self._load_json_list(
            self.tags_json
        )


    @property
    def deadlines(self):
        return self._load_json_list(
            self.deadlines_json
        )


    @property
    def decisions(self):
        return self._load_json_list(
            self.decisions_json
        )


    @property
    def questions(self):
        return self._load_json_list(
            self.questions_json
        )

    @property
    def insights(self):
        """Return the new user-friendly analysis structure."""

        parsed = self._load_json_object(self.insights_json)
        if parsed:
            return parsed

        # Backward-compatible fallback for analyses created before insights_json.
        return {
            "headline": "LifeOS analysis",
            "overview": self.summary or "",
            "attention_level": "Low",
            "analysis_mode": "note_only",
            "project_context": {
                "project_id": None,
                "project_title": "",
                "total_project_tasks": 0,
                "tasks_considered": 0,
                "related_notes_considered": 0,
                "context_limited": False,
            },
            "project_alignment": None,
            "current_project_situation": None,
            "existing_task_matches": [],
            "new_work_not_tracked": [],
            "task_actions": [],
            "recommended_next_step": None,
            "key_points": [],
            "decisions": [
                {"decision": item, "evidence": ""}
                for item in self.decisions
            ],
            "deadlines": self.deadlines,
            "risks_or_blockers": [],
            "missing_information": [
                {"question": item, "why_it_matters": ""}
                for item in self.questions
            ],
            "action_plan": [],
            "tags": self.tags,
        }

    @staticmethod
    def _load_json_list(value):
        if not value:
            return []

        try:
            parsed_value = json.loads(value)

            if isinstance(parsed_value, list):
                return parsed_value

        except (json.JSONDecodeError, TypeError):
            pass

        return []

    @staticmethod
    def _load_json_object(value):
        if not value:
            return {}

        try:
            parsed_value = json.loads(value)
            if isinstance(parsed_value, dict):
                return parsed_value
        except (json.JSONDecodeError, TypeError):
            pass

        return {}

    def __repr__(self):
        return (
            f"<NoteAIAnalysis note_id={self.note_id} "
            f"status={self.status}>"
        )


class NoteAIQuestion(db.Model):
    __tablename__ = "note_ai_questions"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    note_id = db.Column(
        db.Integer,
        db.ForeignKey("notes.id"),
        nullable=False,
        index=True,
    )

    analysis_id = db.Column(
        db.Integer,
        db.ForeignKey("note_ai_analyses.id"),
        nullable=True,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    question = db.Column(
        db.UnicodeText,
        nullable=False,
    )

    answer = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    provider = db.Column(
        db.Unicode(30),
        nullable=False,
    )

    model = db.Column(
        db.Unicode(100),
        nullable=False,
    )

    status = db.Column(
        db.Unicode(20),
        nullable=False,
        default="Completed",
    )

    error_message = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    note = db.relationship(
        "Note",
        back_populates="ai_questions",
        foreign_keys=[note_id],
    )

    analysis = db.relationship(
        "NoteAIAnalysis",
        back_populates="questions_history",
        foreign_keys=[analysis_id],
    )

    user = db.relationship(
        "User",
        back_populates="note_ai_questions",
        foreign_keys=[user_id],
    )

    def __repr__(self):
        return (
            f"<NoteAIQuestion note_id={self.note_id} "
            f"status={self.status}>"
        )
    


class AITaskSuggestion(db.Model):
    __tablename__ = "ai_task_suggestions"

    id = db.Column(db.Integer, primary_key=True)

    analysis_id = db.Column(
        db.Integer,
        db.ForeignKey("note_ai_analyses.id"),
        nullable=False,
        index=True,
    )
    note_id = db.Column(
        db.Integer,
        db.ForeignKey("notes.id"),
        nullable=False,
        index=True,
    )

    title = db.Column(
        db.Unicode(255),
        nullable=False,
    )
    description = db.Column(
        db.UnicodeText,
        nullable=True,
    )
    priority = db.Column(
        db.Unicode(20),
        nullable=False,
        default="Medium",
    )
    deadline = db.Column(db.Date, nullable=True)
    status = db.Column(
        db.Unicode(20),
        nullable=False,
        default="Pending",
    )

    created_task_id = db.Column(
        db.Integer,
        db.ForeignKey("tasks.id"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    analysis = db.relationship(
        "NoteAIAnalysis",
        back_populates="task_suggestions",
    )
    note = db.relationship(
        "Note",
        back_populates="task_suggestions",
    )
    created_task = db.relationship(
        "Task",
        foreign_keys=[created_task_id],
    )


    @property
    def is_pending(self):
        return self.status == "Pending"

    @property
    def is_approved(self):
        return self.status == "Approved"

    @property
    def is_rejected(self):
        return self.status == "Rejected"

    def __repr__(self):
        return (
            f"<AITaskSuggestion {self.title} "
            f"status={self.status}>"
        )


class DocumentVersionFamily(db.Model):
    """One logical document with an immutable history of uploaded versions."""

    __tablename__ = "document_version_families"

    id = db.Column(db.Integer, primary_key=True)

    project_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "projects.id",
            ondelete="NO ACTION",
        ),
        nullable=True,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="NO ACTION",
        ),
        nullable=False,
        index=True,
    )

    name = db.Column(
        db.Unicode(255),
        nullable=False,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    project = db.relationship(
        "Project",
        back_populates="document_version_families",
    )

    user = db.relationship(
        "User",
        back_populates="document_version_families",
    )

    documents = db.relationship(
        "Document",
        back_populates="version_family",
        lazy=True,
        order_by="Document.version_number",
    )

    def __repr__(self):
        return (
            f"<DocumentVersionFamily id={self.id} "
            f"name={self.name!r}>"
        )


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="NO ACTION"),
        # Kept nullable in ORM metadata for backward-compatible test fixtures;
        # migration 20260828_0003 backfills and enforces NOT NULL in production.
        nullable=True,
        index=True,
    )
    owner = db.relationship(
        "User",
        back_populates="documents",
        foreign_keys=[user_id],
    )

    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id"),
        nullable=True,
    )

    version_family_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "document_version_families.id",
            ondelete="NO ACTION",
        ),
        nullable=True,
        index=True,
    )

    version_number = db.Column(
        db.Integer,
        nullable=True,
    )

    is_current_version = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    version_change_json = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    superseded_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    filename = db.Column(
        db.Unicode(255),
        nullable=False,
    )
    file_path = db.Column(
        db.Unicode(500),
        nullable=False,
    )
    extracted_text = db.Column(db.UnicodeText, nullable=True)

    # Step 15 — OCR state is persisted independently from RAG/indexing state.
    # Native PDFs stay ``not_needed``; scanned or mixed PDFs become ``pending``
    # until the OCR workflow is queued and processed.
    ocr_status = db.Column(
        db.Unicode(24),
        nullable=False,
        default="not_needed",
        index=True,
    )
    ocr_provider = db.Column(db.Unicode(64), nullable=True)
    ocr_started_at = db.Column(db.DateTime, nullable=True)
    ocr_completed_at = db.Column(db.DateTime, nullable=True)
    ocr_total_pages = db.Column(db.Integer, nullable=False, default=0)
    ocr_pages_requested = db.Column(db.Integer, nullable=False, default=0)
    ocr_pages_processed = db.Column(db.Integer, nullable=False, default=0)
    ocr_low_confidence_pages = db.Column(db.Integer, nullable=False, default=0)
    ocr_average_confidence = db.Column(db.Float, nullable=True)
    ocr_error = db.Column(db.UnicodeText, nullable=True)
    ocr_layout_json = db.Column(db.UnicodeText, nullable=True)
    # Step 15f — aggregate OCR observability. These describe the *volume* of
    # text OCR actually produced so a completed run can still be flagged as
    # low-quality instead of being trusted just because it did not throw.
    ocr_total_characters = db.Column(db.Integer, nullable=False, default=0)
    ocr_total_words = db.Column(db.Integer, nullable=False, default=0)
    ocr_quality = db.Column(db.Unicode(16), nullable=True)

    summary = db.Column(db.UnicodeText, nullable=True)
    detected_modules = db.Column(db.UnicodeText, nullable=True)
    extracted_tasks = db.Column(db.UnicodeText, nullable=True)
    uploaded_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
    )
    analyses = db.relationship(
    "DocumentAIAnalysis",
    back_populates="document",
    lazy=True,
    cascade="all, delete-orphan",
    )

    task_suggestions = db.relationship(
    "DocumentTaskSuggestion",
    back_populates="document",
    lazy=True,
    cascade="all, delete-orphan",
    )

    questions = db.relationship(
    "DocumentQuestion",
    back_populates="document",
    lazy=True,
    cascade="all, delete-orphan",
    )
    chunks = db.relationship(
    "DocumentChunk",
    back_populates="document",
    lazy=True,
    cascade="all, delete-orphan",
    order_by="DocumentChunk.chunk_index",
    )

    tables = db.relationship(
        "DocumentTable",
        back_populates="document",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="DocumentTable.page_number, DocumentTable.table_index",
    )

    collection_items = db.relationship(
        "DocumentCollectionItem",
        back_populates="document",
        lazy=True,
        passive_deletes=True,
    )

    module_links = db.relationship(
        "ModuleDocumentLink",
        back_populates="document",
        lazy=True,
        passive_deletes=True,
    )

    version_family = db.relationship(
        "DocumentVersionFamily",
        back_populates="documents",
    )

    @property
    def is_versioned(self) -> bool:
        return self.version_family_id is not None

    @property
    def is_historical_version(self) -> bool:
        return bool(
            self.version_family_id is not None
            and not self.is_current_version
        )

    @property
    def version_label(self) -> str:
        if self.version_number:
            return f"Version {self.version_number}"
        return "Current document"

    @property
    def version_change(self) -> dict:
        if not self.version_change_json:
            return {}

        try:
            parsed = json.loads(
                self.version_change_json
            )
        except (
            json.JSONDecodeError,
            TypeError,
        ):
            return {}

        return parsed if isinstance(parsed, dict) else {}

    def __repr__(self):
        return f"<Document {self.filename}>"


@event.listens_for(Document, "before_insert")
def _backfill_document_owner_for_legacy_project_rows(mapper, connection, target):
    """Keep old project-based constructors compatible while ownership moves to Document."""
    if target.user_id is not None or target.project_id is None:
        return
    target.user_id = connection.execute(
        select(Project.user_id).where(Project.id == target.project_id)
    ).scalar_one_or_none()


class DocumentAIAnalysis(db.Model):
    """Stored structured understanding of a project document."""

    __tablename__ = "document_ai_analyses"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    document_id = db.Column(
        db.Integer,
        db.ForeignKey("documents.id"),
        nullable=False,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    provider = db.Column(
        db.Unicode(30),
        nullable=False,
    )

    model = db.Column(
        db.Unicode(100),
        nullable=False,
    )

    status = db.Column(
        db.Unicode(20),
        nullable=False,
        default="Completed",
    )

    document_type = db.Column(
        db.Unicode(80),
        nullable=True,
    )

    summary = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    insights_json = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    source_fingerprint = db.Column(
        db.Unicode(64),
        nullable=True,
    )

    error_message = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    document = db.relationship(
        "Document",
        back_populates="analyses",
    )
    user = db.relationship(
        "User",
       back_populates="document_ai_analyses",
    )

    task_suggestions = db.relationship(
    "DocumentTaskSuggestion",
    back_populates="analysis",
    lazy=True,
    cascade="all, delete-orphan",
    )


    @property
    def insights(self) -> dict:
        """Return the saved structured document insights."""

        if not self.insights_json:
            return {}

        try:
            parsed = json.loads(
                self.insights_json
            )
        except (
            json.JSONDecodeError,
            TypeError,
        ):
            return {}

        return parsed if isinstance(parsed, dict) else {}


    def __repr__(self):
        return (
            f"<DocumentAIAnalysis "
            f"document_id={self.document_id} "
            f"status={self.status}>"
        )

class DocumentTaskSuggestion(db.Model):
    """An action detected from a document awaiting user approval."""

    __tablename__ = "document_task_suggestions"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    analysis_id = db.Column(
        db.Integer,
        db.ForeignKey("document_ai_analyses.id"),
        nullable=False,
        index=True,
    )

    document_id = db.Column(
        db.Integer,
        db.ForeignKey("documents.id"),
        nullable=False,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    title = db.Column(
        db.Unicode(255),
        nullable=False,
    )

    description = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    tags = db.Column(
        db.Unicode(500),
        nullable=True,
    )

    priority = db.Column(
        db.Unicode(20),
        nullable=False,
        default="Medium",
    )

    deadline = db.Column(
        db.Date,
        nullable=True,
    )

    source_json = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    status = db.Column(
        db.Unicode(20),
        nullable=False,
        default="Pending",
        index=True,
    )

    matched_task_id = db.Column(
        db.Integer,
        db.ForeignKey("tasks.id"),
        nullable=True,
        index=True,
    )

    match_score = db.Column(
        db.Float,
        nullable=False,
        default=0.0,
    )

    created_task_id = db.Column(
        db.Integer,
        db.ForeignKey("tasks.id"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    analysis = db.relationship(
        "DocumentAIAnalysis",
        back_populates="task_suggestions",
    )

    document = db.relationship(
        "Document",
        back_populates="task_suggestions",
    )

    user = db.relationship(
        "User",
        back_populates="document_task_suggestions",
    )

    matched_task = db.relationship(
        "Task",
        foreign_keys=[matched_task_id],
    )

    created_task = db.relationship(
        "Task",
        foreign_keys=[created_task_id],
    )

    @property
    def source(self) -> dict:
        """Return the saved page and evidence information."""

        if not self.source_json:
            return {}

        try:
            parsed = json.loads(
                self.source_json
            )
        except (
            json.JSONDecodeError,
            TypeError,
        ):
            return {}

        return parsed if isinstance(parsed, dict) else {}

    @property
    def lifecycle_label(self) -> str:
        """Return the user-facing Step 9 lifecycle label."""

        return {
            "Pending": "Suggested",
            "Approved": "Created",
            "Linked": "Existing task",
            "Rejected": "Ignored",
            "Outdated": "Outdated",
        }.get(self.status, self.status or "Suggested")

    @property
    def tags_list(self) -> list[str]:
        if not self.tags:
            return []

        return [
            item.strip()
            for item in self.tags.split(",")
            if item.strip()
        ]

    @property
    def is_actionable(self) -> bool:
        return self.status == "Pending"

    def __repr__(self):
        return (
            f"<DocumentTaskSuggestion "
            f"id={self.id} status={self.status}>"
        )


class ProjectQuestion(db.Model):
    """A grounded answer produced from all readable PDFs in one project."""

    __tablename__ = "project_questions"

    id = db.Column(db.Integer, primary_key=True)

    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id"),
        nullable=False,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    question = db.Column(
        db.Unicode(2000),
        nullable=False,
    )

    answer = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    sources_json = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    provider = db.Column(
        db.Unicode(30),
        nullable=False,
    )

    model = db.Column(
        db.Unicode(100),
        nullable=False,
    )

    status = db.Column(
        db.Unicode(20),
        nullable=False,
        default="Completed",
        index=True,
    )

    source_fingerprint = db.Column(
        db.Unicode(64),
        nullable=True,
    )

    error_message = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    project = db.relationship(
        "Project",
        back_populates="project_questions",
    )

    user = db.relationship(
        "User",
        back_populates="project_questions",
    )

    @property
    def sources(self) -> list:
        if not self.sources_json:
            return []

        try:
            parsed = json.loads(self.sources_json)
        except (json.JSONDecodeError, TypeError):
            return []

        return parsed if isinstance(parsed, list) else []

    def __repr__(self):
        return (
            f"<ProjectQuestion id={self.id} "
            f"project_id={self.project_id} status={self.status}>"
        )


class DocumentComparison(db.Model):
    """A saved semantic comparison between two owned documents."""

    __tablename__ = "document_comparisons"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # SQL Server does not allow both document foreign keys to cascade into
    # the same table. The application explicitly removes comparisons before
    # deleting a project/document, so both document relationships use
    # symmetric NO ACTION behavior.
    document_a_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "documents.id",
            ondelete="NO ACTION",
        ),
        nullable=False,
        index=True,
    )

    document_b_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "documents.id",
            ondelete="NO ACTION",
        ),
        nullable=False,
        index=True,
    )

    summary = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    findings_json = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    provider = db.Column(
        db.Unicode(30),
        nullable=False,
    )

    model = db.Column(
        db.Unicode(100),
        nullable=False,
    )

    status = db.Column(
        db.Unicode(20),
        nullable=False,
        default="Pending",
        index=True,
    )

    source_fingerprint = db.Column(
        db.Unicode(64),
        nullable=True,
    )

    error_message = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    user = db.relationship(
        "User",
        back_populates="document_comparisons",
    )

    document_a = db.relationship(
        "Document",
        foreign_keys=[document_a_id],
    )

    document_b = db.relationship(
        "Document",
        foreign_keys=[document_b_id],
    )

    __table_args__ = (
        db.CheckConstraint(
            "document_a_id <> document_b_id",
            name="ck_document_comparisons_distinct_documents",
        ),
        db.Index(
            "ix_document_comparisons_reuse",
            "user_id",
            "document_a_id",
            "document_b_id",
            "status",
            "source_fingerprint",
        ),
    )

    @property
    def findings(self) -> list:
        """Return saved comparison findings as a safe list."""

        if not self.findings_json:
            return []

        try:
            parsed = json.loads(
                self.findings_json
            )
        except (
            json.JSONDecodeError,
            TypeError,
        ):
            return []

        return (
            parsed
            if isinstance(parsed, list)
            else []
        )

    def __repr__(self):
        return (
            f"<DocumentComparison id={self.id} "
            f"document_a_id={self.document_a_id} "
            f"document_b_id={self.document_b_id} "
            f"status={self.status}>"
        )


class DocumentQuestion(db.Model):
    """A grounded question and answer about one document."""

    __tablename__ = "document_questions"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    document_id = db.Column(
        db.Integer,
        db.ForeignKey("documents.id"),
        nullable=False,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    question = db.Column(
        db.Unicode(2000),
        nullable=False,
    )

    answer = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    sources_json = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    provider = db.Column(
        db.Unicode(30),
        nullable=False,
    )

    model = db.Column(
        db.Unicode(100),
        nullable=False,
    )

    status = db.Column(
        db.Unicode(20),
        nullable=False,
        default="Completed",
        index=True,
    )

    source_fingerprint = db.Column(
        db.Unicode(64),
        nullable=True,
    )

    error_message = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    document = db.relationship(
        "Document",
        back_populates="questions",
    )

    user = db.relationship(
        "User",
        back_populates="document_questions",
    )

    @property
    def sources(self) -> list:
        """Return saved page references for the answer."""

        if not self.sources_json:
            return []

        try:
            parsed = json.loads(
                self.sources_json
            )
        except (
            json.JSONDecodeError,
            TypeError,
        ):
            return []

        return parsed if isinstance(parsed, list) else []

    def __repr__(self):
        return (
            f"<DocumentQuestion "
            f"id={self.id} status={self.status}>"
        )


class DocumentChunk(db.Model):
    """
    A searchable page-based section of an extracted document.

    Keyword retrieval uses the text directly. Semantic retrieval
    uses the optional stored embedding.
    """

    __tablename__ = "document_chunks"

    __table_args__ = (
        db.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunk_index",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    document_id = db.Column(
        db.Integer,
        db.ForeignKey("documents.id"),
        nullable=False,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    chunk_index = db.Column(
        db.Integer,
        nullable=False,
    )

    page_start = db.Column(
        db.Integer,
        nullable=True,
    )

    page_end = db.Column(
        db.Integer,
        nullable=True,
    )

    section_title = db.Column(
        db.Unicode(255),
        nullable=True,
    )

    # Step 16 — table-aware chunks still use the one existing RAG pipeline.
    content_type = db.Column(
        db.Unicode(20),
        nullable=False,
        default="text",
        index=True,
    )

    table_id = db.Column(
        db.Integer,
        db.ForeignKey("document_tables.id", ondelete="NO ACTION"),
        nullable=True,
        index=True,
    )

    text = db.Column(
        db.UnicodeText,
        nullable=False,
    )

    character_count = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    source_fingerprint = db.Column(
        db.Unicode(64),
        nullable=False,
        index=True,
    )

    # Semantic retrieval fields.
    #
    # The embedding is stored as JSON during the first implementation,
    # allowing LifeOS to keep using the current SQL Server database.
    embedding_json = db.Column(
        db.UnicodeText,
        nullable=True,
    )

    embedding_provider = db.Column(
        db.Unicode(30),
        nullable=True,
    )

    embedding_model = db.Column(
        db.Unicode(100),
        nullable=True,
    )

    embedding_dimensions = db.Column(
        db.Integer,
        nullable=True,
    )

    embedding_fingerprint = db.Column(
        db.Unicode(64),
        nullable=True,
    )

    embedded_at = db.Column(
        db.DateTime,
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    document = db.relationship(
        "Document",
        back_populates="chunks",
    )

    user = db.relationship(
        "User",
        back_populates="document_chunks",
    )

    table = db.relationship(
        "DocumentTable",
        back_populates="chunks",
    )

    @property
    def embedding(self) -> list[float]:
        """Return the saved embedding as a validated list of floats."""

        if not self.embedding_json:
            return []

        try:
            parsed_embedding = json.loads(
                self.embedding_json
            )

        except (
            json.JSONDecodeError,
            TypeError,
        ):
            return []

        if not isinstance(
            parsed_embedding,
            list,
        ):
            return []

        try:
            values = [
                float(value)
                for value in parsed_embedding
            ]

        except (
            TypeError,
            ValueError,
        ):
            return []

        if (
            self.embedding_dimensions is not None
            and len(values) != self.embedding_dimensions
        ):
            return []

        return values

    @property
    def has_embedding(self) -> bool:
        """Return whether this chunk has complete embedding metadata."""

        return bool(
            self.embedding
            and self.embedding_provider
            and self.embedding_model
            and self.embedding_dimensions
            and self.embedding_fingerprint
            and self.embedded_at
        )

    def clear_embedding(self) -> None:
        """Remove a stale or invalid embedding from this chunk."""

        self.embedding_json = None
        self.embedding_provider = None
        self.embedding_model = None
        self.embedding_dimensions = None
        self.embedding_fingerprint = None
        self.embedded_at = None

    def __repr__(self):
        return (
            f"<DocumentChunk "
            f"document_id={self.document_id} "
            f"index={self.chunk_index} "
            f"page={self.page_start}>"
        )

class DocumentTable(db.Model):
    """Structured table extracted from one PDF page (Step 16)."""

    __tablename__ = "document_tables"
    __table_args__ = (
        db.UniqueConstraint(
            "document_id", "page_number", "table_index",
            name="uq_document_table_page_index",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=False, index=True,
    )
    page_number = db.Column(db.Integer, nullable=False, index=True)
    table_index = db.Column(db.Integer, nullable=False)
    title = db.Column(db.Unicode(255), nullable=True)
    headers_json = db.Column(db.UnicodeText, nullable=True)
    rows_json = db.Column(db.UnicodeText, nullable=False)
    markdown_text = db.Column(db.UnicodeText, nullable=False)
    row_count = db.Column(db.Integer, nullable=False, default=0)
    column_count = db.Column(db.Integer, nullable=False, default=0)
    source_fingerprint = db.Column(db.Unicode(64), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    document = db.relationship("Document", back_populates="tables")
    chunks = db.relationship("DocumentChunk", back_populates="table", lazy=True)

    @property
    def headers(self) -> list:
        try:
            parsed = json.loads(self.headers_json or "[]")
        except (json.JSONDecodeError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else []

    @property
    def rows(self) -> list:
        try:
            parsed = json.loads(self.rows_json or "[]")
        except (json.JSONDecodeError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else []


class DocumentCollection(db.Model):
    """User-defined document group queried with the existing grounded RAG stack."""

    __tablename__ = "document_collections"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=False, index=True,
    )
    name = db.Column(db.Unicode(150), nullable=False)
    description = db.Column(db.UnicodeText, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    items = db.relationship(
        "DocumentCollectionItem", back_populates="collection", lazy=True,
        cascade="all, delete-orphan", order_by="DocumentCollectionItem.added_at",
    )
    questions = db.relationship(
        "DocumentCollectionQuestion", back_populates="collection", lazy=True,
        cascade="all, delete-orphan",
    )


class DocumentCollectionItem(db.Model):
    __tablename__ = "document_collection_items"
    __table_args__ = (
        db.UniqueConstraint(
            "collection_id", "document_id", name="uq_document_collection_item"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    collection_id = db.Column(
        db.Integer, db.ForeignKey("document_collections.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    added_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    collection = db.relationship("DocumentCollection", back_populates="items")
    document = db.relationship("Document", back_populates="collection_items")


class DocumentCollectionQuestion(db.Model):
    __tablename__ = "document_collection_questions"

    id = db.Column(db.Integer, primary_key=True)
    collection_id = db.Column(
        db.Integer, db.ForeignKey("document_collections.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=False, index=True,
    )
    question = db.Column(db.Unicode(2000), nullable=False)
    answer = db.Column(db.UnicodeText, nullable=True)
    sources_json = db.Column(db.UnicodeText, nullable=True)
    provider = db.Column(db.Unicode(30), nullable=False)
    model = db.Column(db.Unicode(100), nullable=False)
    status = db.Column(db.Unicode(20), nullable=False, default="Completed", index=True)
    source_fingerprint = db.Column(db.Unicode(64), nullable=True)
    error_message = db.Column(db.UnicodeText, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    collection = db.relationship("DocumentCollection", back_populates="questions")

    @property
    def sources(self) -> list:
        try:
            parsed = json.loads(self.sources_json or "[]")
        except (json.JSONDecodeError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else []



class LearningModule(db.Model):
    """Knowledge-driven workspace containing lectures and shared LifeOS resources."""

    __tablename__ = "learning_modules"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=False, index=True,
    )
    title = db.Column(db.Unicode(150), nullable=False)
    description = db.Column(db.UnicodeText, nullable=True)
    subject = db.Column(db.Unicode(150), nullable=True)
    status = db.Column(db.Unicode(32), nullable=False, default="Active", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    owner = db.relationship("User", back_populates="modules")
    lectures = db.relationship(
        "Lecture", back_populates="module", lazy=True,
        cascade="all, delete-orphan", order_by="Lecture.lecture_number, Lecture.id",
    )
    document_links = db.relationship(
        "ModuleDocumentLink", back_populates="module", lazy=True,
        cascade="all, delete-orphan",
    )
    note_links = db.relationship(
        "ModuleNoteLink", back_populates="module", lazy=True,
        cascade="all, delete-orphan",
    )
    task_links = db.relationship(
        "ModuleTaskLink", back_populates="module", lazy=True,
        cascade="all, delete-orphan",
    )
    collection_links = db.relationship(
        "ModuleCollectionLink", back_populates="module", lazy=True,
        cascade="all, delete-orphan",
    )
    questions = db.relationship(
        "ModuleQuestion", back_populates="module", lazy=True,
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<LearningModule {self.title}>"


class Lecture(db.Model):
    __tablename__ = "lectures"
    __table_args__ = (
        db.UniqueConstraint("module_id", "lecture_number", name="uq_module_lecture_number"),
    )

    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(
        db.Integer, db.ForeignKey("learning_modules.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    title = db.Column(db.Unicode(180), nullable=False)
    lecture_number = db.Column(db.Integer, nullable=True)
    lecture_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.Unicode(32), nullable=False, default="Planned", index=True)
    topics = db.Column(db.UnicodeText, nullable=True)
    summary = db.Column(db.UnicodeText, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    module = db.relationship("LearningModule", back_populates="lectures")
    document_links = db.relationship(
        "ModuleDocumentLink", back_populates="lecture", lazy=True,
        foreign_keys="ModuleDocumentLink.lecture_id",
    )
    note_links = db.relationship(
        "ModuleNoteLink", back_populates="lecture", lazy=True,
        foreign_keys="ModuleNoteLink.lecture_id",
    )
    task_links = db.relationship(
        "ModuleTaskLink", back_populates="lecture", lazy=True,
        foreign_keys="ModuleTaskLink.lecture_id",
    )
    questions = db.relationship(
        "ModuleQuestion", back_populates="lecture", lazy=True,
        foreign_keys="ModuleQuestion.lecture_id",
    )

    def __repr__(self):
        return f"<Lecture module={self.module_id} number={self.lecture_number} title={self.title!r}>"


class ModuleDocumentLink(db.Model):
    __tablename__ = "module_document_links"
    __table_args__ = (
        db.UniqueConstraint("module_id", "document_id", name="uq_module_document_link"),
    )

    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(
        db.Integer, db.ForeignKey("learning_modules.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    lecture_id = db.Column(
        db.Integer, db.ForeignKey("lectures.id", ondelete="NO ACTION"),
        nullable=True, index=True,
    )
    added_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    module = db.relationship("LearningModule", back_populates="document_links")
    lecture = db.relationship("Lecture", back_populates="document_links", foreign_keys=[lecture_id])
    document = db.relationship("Document", back_populates="module_links")


class ModuleNoteLink(db.Model):
    __tablename__ = "module_note_links"
    __table_args__ = (
        db.UniqueConstraint("module_id", "note_id", name="uq_module_note_link"),
    )

    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(
        db.Integer, db.ForeignKey("learning_modules.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    note_id = db.Column(
        db.Integer, db.ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    lecture_id = db.Column(
        db.Integer, db.ForeignKey("lectures.id", ondelete="NO ACTION"),
        nullable=True, index=True,
    )
    added_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    module = db.relationship("LearningModule", back_populates="note_links")
    lecture = db.relationship("Lecture", back_populates="note_links", foreign_keys=[lecture_id])
    note = db.relationship("Note")


class ModuleTaskLink(db.Model):
    __tablename__ = "module_task_links"
    __table_args__ = (
        db.UniqueConstraint("module_id", "task_id", name="uq_module_task_link"),
    )

    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(
        db.Integer, db.ForeignKey("learning_modules.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    task_id = db.Column(
        db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    lecture_id = db.Column(
        db.Integer, db.ForeignKey("lectures.id", ondelete="NO ACTION"),
        nullable=True, index=True,
    )
    added_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    module = db.relationship("LearningModule", back_populates="task_links")
    lecture = db.relationship("Lecture", back_populates="task_links", foreign_keys=[lecture_id])
    task = db.relationship("Task")


class ModuleCollectionLink(db.Model):
    __tablename__ = "module_collection_links"
    __table_args__ = (
        db.UniqueConstraint("module_id", "collection_id", name="uq_module_collection_link"),
    )

    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(
        db.Integer, db.ForeignKey("learning_modules.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    collection_id = db.Column(
        db.Integer, db.ForeignKey("document_collections.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    added_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    module = db.relationship("LearningModule", back_populates="collection_links")
    collection = db.relationship("DocumentCollection")


class ModuleQuestion(db.Model):
    __tablename__ = "module_questions"

    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(
        db.Integer, db.ForeignKey("learning_modules.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    lecture_id = db.Column(
        db.Integer, db.ForeignKey("lectures.id", ondelete="NO ACTION"),
        nullable=True, index=True,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=False, index=True,
    )
    question = db.Column(db.Unicode(2000), nullable=False)
    answer = db.Column(db.UnicodeText, nullable=True)
    sources_json = db.Column(db.UnicodeText, nullable=True)
    provider = db.Column(db.Unicode(30), nullable=False)
    model = db.Column(db.Unicode(100), nullable=False)
    status = db.Column(db.Unicode(20), nullable=False, default="Completed", index=True)
    source_fingerprint = db.Column(db.Unicode(64), nullable=True)
    error_message = db.Column(db.UnicodeText, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    module = db.relationship("LearningModule", back_populates="questions")
    lecture = db.relationship("Lecture", back_populates="questions", foreign_keys=[lecture_id])
    user = db.relationship("User", back_populates="module_questions")

    @property
    def sources(self) -> list:
        try:
            parsed = json.loads(self.sources_json or "[]")
        except (json.JSONDecodeError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else []


class LifeOSActionProposal(db.Model):
    """User-owned, confirmation-gated action prepared by LifeOS intelligence."""

    __tablename__ = "lifeos_action_proposals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=False,
        index=True,
    )
    action_type = db.Column(db.Unicode(64), nullable=False, index=True)
    status = db.Column(db.Unicode(24), nullable=False, default="pending", index=True)
    title = db.Column(db.Unicode(255), nullable=False)
    reason = db.Column(db.UnicodeText, nullable=True)
    target_type = db.Column(db.Unicode(64), nullable=False)
    target_id = db.Column(db.Integer, nullable=True)
    # Historical audit/proposal records must not block project deletion.
    # Ownership is revalidated before execution; this is an informational ID.
    project_id = db.Column(db.Integer, nullable=True, index=True)
    payload_json = db.Column(db.UnicodeText, nullable=False, default="{}")
    evidence_json = db.Column(db.UnicodeText, nullable=False, default="[]")
    risk_level = db.Column(db.Unicode(24), nullable=False, default="medium")
    requires_confirmation = db.Column(db.Boolean, nullable=False, default=True)
    execution_resource_type = db.Column(db.Unicode(64), nullable=True)
    execution_resource_id = db.Column(db.Integer, nullable=True)
    failure_message = db.Column(db.UnicodeText, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    resolved_at = db.Column(db.DateTime, nullable=True)

    @property
    def payload(self) -> dict:
        try:
            parsed = json.loads(self.payload_json or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @property
    def evidence(self) -> list:
        try:
            parsed = json.loads(self.evidence_json or "[]")
        except (json.JSONDecodeError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else []


class LifeOSActivityEvent(db.Model):
    """Auditable, user-owned record of meaningful workspace changes."""

    __tablename__ = "lifeos_activity_events"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=False,
        index=True,
    )
    event_type = db.Column(db.Unicode(80), nullable=False, index=True)
    object_type = db.Column(db.Unicode(64), nullable=False, index=True)
    object_id = db.Column(db.Integer, nullable=True)
    # Keep historical activity after a project is removed without a FK blocker.
    project_id = db.Column(db.Integer, nullable=True, index=True)
    title = db.Column(db.Unicode(255), nullable=False)
    summary = db.Column(db.UnicodeText, nullable=True)
    changes_json = db.Column(db.UnicodeText, nullable=False, default="{}")
    source_type = db.Column(db.Unicode(64), nullable=False, default="user")
    source_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    @property
    def changes(self) -> dict:
        try:
            parsed = json.loads(self.changes_json or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}


class LifeOSContextLink(db.Model):
    """User-owned first-class relationship between two LifeOS resources.

    Polymorphic resource IDs intentionally do not use cross-table foreign keys.
    Ownership is validated by the context-link service before links are created
    or exposed.  This keeps historical/provenance relationships from blocking
    normal resource deletion on SQL Server while still enforcing a user FK.
    """

    __tablename__ = "lifeos_context_links"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "source_type",
            "source_id",
            "target_type",
            "target_id",
            "relation_type",
            name="uq_lifeos_context_link_edge",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=False,
        index=True,
    )
    source_type = db.Column(db.Unicode(40), nullable=False, index=True)
    source_id = db.Column(db.Integer, nullable=False, index=True)
    target_type = db.Column(db.Unicode(40), nullable=False, index=True)
    target_id = db.Column(db.Integer, nullable=False, index=True)
    relation_type = db.Column(db.Unicode(48), nullable=False, index=True)
    reason = db.Column(db.UnicodeText, nullable=True)
    provenance_type = db.Column(db.Unicode(48), nullable=False, default="user")
    provenance_id = db.Column(db.Integer, nullable=True)
    evidence_json = db.Column(db.UnicodeText, nullable=False, default="[]")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    @property
    def evidence(self) -> list:
        try:
            parsed = json.loads(self.evidence_json or "[]")
        except (json.JSONDecodeError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else []


class LifeOSIntelligenceEvent(db.Model):
    """I14 normalized event detected from trusted LifeOS state.

    Events are user-owned and deliberately separate from raw activity history.
    State events (for example ``task.overdue``) stay open while the condition is
    true and are resolved on a later scan. Point-in-time events are stored as
    observed history. No event is allowed to mutate workspace resources.
    """

    __tablename__ = "lifeos_intelligence_events"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "dedupe_key",
            name="uq_lifeos_intelligence_event_dedupe",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=False,
        index=True,
    )
    event_type = db.Column(db.Unicode(80), nullable=False, index=True)
    severity = db.Column(db.Unicode(24), nullable=False, default="normal", index=True)
    lifecycle = db.Column(db.Unicode(24), nullable=False, default="open", index=True)
    object_type = db.Column(db.Unicode(64), nullable=False, index=True)
    object_id = db.Column(db.Integer, nullable=True)
    project_id = db.Column(db.Integer, nullable=True, index=True)
    title = db.Column(db.Unicode(255), nullable=False)
    summary = db.Column(db.UnicodeText, nullable=True)
    dedupe_key = db.Column(db.Unicode(255), nullable=False)
    context_json = db.Column(db.UnicodeText, nullable=False, default="{}")
    source_type = db.Column(db.Unicode(64), nullable=False, default="state_scan")
    source_id = db.Column(db.Integer, nullable=True)
    detected_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    @property
    def context(self) -> dict:
        try:
            parsed = json.loads(self.context_json or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}


class LifeOSProactiveNotification(db.Model):
    """I15 in-app notification generated from one normalized I14 event.

    This is a suggestion/attention surface only. It never executes an I9 action
    or writes to Task/Project/Document/Note state by itself.
    """

    __tablename__ = "lifeos_proactive_notifications"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "event_id",
            name="uq_lifeos_proactive_notification_event",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=False,
        index=True,
    )
    event_id = db.Column(
        db.Integer,
        db.ForeignKey("lifeos_intelligence_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category = db.Column(db.Unicode(64), nullable=False, default="attention", index=True)
    severity = db.Column(db.Unicode(24), nullable=False, default="normal", index=True)
    status = db.Column(db.Unicode(24), nullable=False, default="unread", index=True)
    title = db.Column(db.Unicode(255), nullable=False)
    message = db.Column(db.UnicodeText, nullable=False)
    action_label = db.Column(db.Unicode(80), nullable=True)
    action_href = db.Column(db.Unicode(500), nullable=True)
    ask_query = db.Column(db.Unicode(1000), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    read_at = db.Column(db.DateTime, nullable=True)
    dismissed_at = db.Column(db.DateTime, nullable=True)

    event = db.relationship("LifeOSIntelligenceEvent")


class LifeOSMemory(db.Model):
    """I16 typed, user-owned memory that is always inspectable and deletable."""

    __tablename__ = "lifeos_memories"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "memory_type", "memory_key",
            name="uq_lifeos_memory_key",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=False,
        index=True,
    )
    memory_type = db.Column(db.Unicode(40), nullable=False, index=True)
    memory_key = db.Column(db.Unicode(160), nullable=False, index=True)
    label = db.Column(db.Unicode(180), nullable=False)
    value_json = db.Column(db.UnicodeText, nullable=False, default="{}")
    scope_type = db.Column(db.Unicode(40), nullable=True, index=True)
    scope_id = db.Column(db.Integer, nullable=True, index=True)
    source_type = db.Column(db.Unicode(48), nullable=False, default="user_confirmed", index=True)
    source_id = db.Column(db.Integer, nullable=True)
    user_confirmed = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.Unicode(24), nullable=False, default="active", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True, index=True)

    @property
    def value(self) -> dict:
        try:
            parsed = json.loads(self.value_json or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}


class LifeOSAutomation(db.Model):
    """I17 preparation: user-owned automation definition.

    Automations are intentionally constrained to an allow-listed trigger/action
    registry. The model stores declarative configuration only; it never stores
    executable code, arbitrary SQL, provider prompts, or unrestricted URLs.
    """

    __tablename__ = "lifeos_automations"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "name",
            name="uq_lifeos_automation_user_name",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.Unicode(160), nullable=False)
    description = db.Column(db.UnicodeText, nullable=True)
    enabled = db.Column(db.Boolean, nullable=False, default=False, index=True)
    trigger_type = db.Column(db.Unicode(32), nullable=False, index=True)
    trigger_config_json = db.Column(db.UnicodeText, nullable=False, default="{}")
    action_type = db.Column(db.Unicode(48), nullable=False, index=True)
    action_config_json = db.Column(db.UnicodeText, nullable=False, default="{}")
    visual_graph_json = db.Column(db.UnicodeText, nullable=False, default="{}")
    timezone = db.Column(db.Unicode(80), nullable=False, default="UTC")
    status = db.Column(db.Unicode(24), nullable=False, default="ready", index=True)
    next_run_at = db.Column(db.DateTime, nullable=True, index=True)
    last_run_at = db.Column(db.DateTime, nullable=True)
    last_event_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    @property
    def trigger_config(self) -> dict:
        try:
            parsed = json.loads(self.trigger_config_json or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @property
    def action_config(self) -> dict:
        try:
            parsed = json.loads(self.action_config_json or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @property
    def visual_graph(self) -> dict:
        try:
            parsed = json.loads(self.visual_graph_json or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}


class LifeOSAutomationRun(db.Model):
    """Immutable-ish audit record for one I17 automation evaluation/execution."""

    __tablename__ = "lifeos_automation_runs"

    id = db.Column(db.Integer, primary_key=True)
    automation_id = db.Column(
        db.Integer,
        db.ForeignKey("lifeos_automations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="NO ACTION"),
        nullable=False,
        index=True,
    )
    status = db.Column(db.Unicode(24), nullable=False, default="prepared", index=True)
    trigger_source = db.Column(db.Unicode(32), nullable=False, default="manual", index=True)
    event_id = db.Column(db.Integer, nullable=True)
    dry_run = db.Column(db.Boolean, nullable=False, default=True)
    output_json = db.Column(db.UnicodeText, nullable=False, default="{}")
    error_message = db.Column(db.UnicodeText, nullable=True)
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    finished_at = db.Column(db.DateTime, nullable=True)

    automation = db.relationship("LifeOSAutomation", backref=db.backref("runs", lazy=True, cascade="all, delete-orphan"))

    @property
    def output(self) -> dict:
        try:
            parsed = json.loads(self.output_json or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

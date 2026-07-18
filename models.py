from datetime import datetime

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

    title = db.Column(db.Unicode(200), nullable=False)
    description = db.Column(db.UnicodeText, nullable=True)
    module = db.Column(db.Unicode(100), nullable=True)
    importance = db.Column(db.Unicode(50), default="Medium")
    difficulty = db.Column(db.Unicode(50), default="Medium")
    deadline = db.Column(db.Date, nullable=True)
    status = db.Column(db.Unicode(50), default="Pending")
    priority_score = db.Column(db.Float, default=0)
    reason = db.Column(db.UnicodeText, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def is_general(self):
        return self.project_id is None

    @property
    def scope_label(self):
        return "General Workspace" if self.is_general else "Project Task"

    def __repr__(self):
        return f"<Task {self.title}>"


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

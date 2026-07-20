import os
from datetime import date

from dotenv import load_dotenv

from flask import (
    Flask,
    redirect,
    render_template,
    url_for
)

from flask_login import (
    LoginManager,
    current_user,
    login_required
)

from flask_migrate import Migrate

from database import db, get_database_uri
from models import (
    Document,
    EmailNotificationLog,
    FocusSession,
    NotificationPreference,
    Note,
    Project,
    Task,
    User
)

from routes.auth_routes import auth_bp
from routes.project_routes import project_bp
from routes.task_routes import task_bp
from routes.notification_routes import notification_bp
from routes.focus_routes import focus_bp
from routes.analytics_routes import analytics_bp
from services.scheduler_service import start_notification_scheduler


load_dotenv()


app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "development-only-secret-key"
)

app.config["SQLALCHEMY_DATABASE_URI"] = (
    get_database_uri()
)

app.config[
    "SQLALCHEMY_TRACK_MODIFICATIONS"
] = False

app.config["TEMPLATES_AUTO_RELOAD"] = True

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"


db.init_app(app)

migrate = Migrate(app, db)


login_manager = LoginManager()

login_manager.login_view = "auth_bp.login"
login_manager.login_message = (
    "Please log in to access your workspace."
)
login_manager.login_message_category = "info"

login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(
            User,
            int(user_id)
        )
    except (TypeError, ValueError):
        return None


app.register_blueprint(auth_bp)
app.register_blueprint(project_bp)
app.register_blueprint(task_bp)
app.register_blueprint(notification_bp)
app.register_blueprint(focus_bp)
app.register_blueprint(analytics_bp)


@app.route("/")
def landing():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    return render_template("landing.html")


@app.route("/dashboard")
@login_required
def dashboard():
    projects = (
        Project.query
        .filter_by(user_id=current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )

    tasks = (
        Task.query
        .filter_by(user_id=current_user.id)
        .all()
    )

    projects_count = len(projects)
    tasks_count = len(tasks)

    general_tasks_count = sum(
        1
        for task in tasks
        if task.project_id is None
    )

    project_tasks_count = tasks_count - general_tasks_count

    active_projects_count = sum(
        1
        for project in projects
        if project.status not in ("Completed", "Paused")
    )

    completed_tasks_count = sum(
        1
        for task in tasks
        if task.status == "Completed"
    )

    blocked_tasks_count = sum(
        1
        for task in tasks
        if task.status == "Blocked"
    )

    open_tasks_count = sum(
        1
        for task in tasks
        if task.status != "Completed"
    )

    overdue_tasks_count = sum(
        1
        for task in tasks
        if (
            task.deadline
            and task.deadline < date.today()
            and task.status != "Completed"
        )
    )

    completion_rate = 0

    if tasks_count:
        completion_rate = round(
            completed_tasks_count / tasks_count * 100
        )

    average_project_progress = 0

    if projects_count:
        average_project_progress = round(
            sum(project.progress or 0 for project in projects)
            / projects_count
        )

    importance_order = {
        "Critical": 4,
        "High": 3,
        "Medium": 2,
        "Low": 1
    }

    focus_candidates = [
        task
        for task in tasks
        if task.status not in ("Completed", "Blocked")
    ]

    def focus_sort_key(task):
        status_rank = (
            0 if task.status == "In Progress" else 1
        )

        deadline_rank = task.deadline or date.max

        return (
            status_rank,
            -importance_order.get(task.importance, 0),
            deadline_rank,
            -(task.priority_score or 0)
        )

    focus_task = None

    if focus_candidates:
        focus_task = sorted(
            focus_candidates,
            key=focus_sort_key
        )[0]

    upcoming_tasks = sorted(
        [
            task
            for task in tasks
            if task.deadline and task.status != "Completed"
        ],
        key=lambda task: task.deadline
    )[:5]

    latest_projects = projects[:4]

    notes_count = (
        Note.query
        .join(
            Project,
            Note.project_id == Project.id
        )
        .filter(Project.user_id == current_user.id)
        .count()
    )

    documents_count = (
        Document.query
        .join(
            Project,
            Document.project_id == Project.id
        )
        .filter(Project.user_id == current_user.id)
        .count()
    )

    return render_template(
        "dashboard.html",
        today=date.today(),
        projects_count=projects_count,
        active_projects_count=active_projects_count,
        tasks_count=tasks_count,
        general_tasks_count=general_tasks_count,
        project_tasks_count=project_tasks_count,
        open_tasks_count=open_tasks_count,
        completed_tasks_count=completed_tasks_count,
        blocked_tasks_count=blocked_tasks_count,
        overdue_tasks_count=overdue_tasks_count,
        completion_rate=completion_rate,
        average_project_progress=average_project_progress,
        notes_count=notes_count,
        documents_count=documents_count,
        focus_task=focus_task,
        upcoming_tasks=upcoming_tasks,
        latest_projects=latest_projects
    )


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    start_notification_scheduler(app)

    print("\nREGISTERED ROUTES:")

    for rule in app.url_map.iter_rules():
        print(rule)

    app.run(
        debug=True,
        use_reloader=False
    )

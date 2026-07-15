from flask import Flask, render_template
from database import db, get_database_uri
from models import Project, Task, Note, Document
from routes.project_routes import project_bp


app = Flask(__name__)

app.config["SECRET_KEY"] = "lifeos_secret_key"
app.config["SQLALCHEMY_DATABASE_URI"] = get_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

app.register_blueprint(project_bp)


@app.route("/")
def dashboard():
    projects_count = Project.query.count()
    tasks_count = Task.query.count()
    notes_count = Note.query.count()
    documents_count = Document.query.count()

    latest_projects = Project.query.order_by(Project.created_at.desc()).limit(3).all()

    return render_template(
        "dashboard.html",
        projects_count=projects_count,
        tasks_count=tasks_count,
        notes_count=notes_count,
        documents_count=documents_count,
        latest_projects=latest_projects
    )


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        # Verification: confirms exactly which columns Flask/SQLAlchemy
        # is working with right now, from the *current* models.py.
        # If a column you added isn't in this list, the model change
        # didn't get picked up (wrong file saved, wrong venv, etc.)
        print("LifeOS database tables are ready.")
        print("Project columns currently mapped by SQLAlchemy:")
        for column in Project.__table__.columns:
            print(f"  - {column.name} ({column.type})")

    app.run(debug=True)

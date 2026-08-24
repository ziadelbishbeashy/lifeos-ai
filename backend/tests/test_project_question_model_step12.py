"""Step 12 ProjectQuestion model tests."""

import json

from database import db
from models import Project, ProjectQuestion


def test_project_question_sources_round_trip(app, user):
    with app.app_context():
        project = Project(user_id=user, title="LifeOS")
        db.session.add(project)
        db.session.flush()

        item = ProjectQuestion(
            project_id=project.id,
            user_id=user,
            question="What are the risks?",
            answer="A risk exists. [Source 1]",
            sources_json=json.dumps([
                {
                    "source_id": 1,
                    "document_id": 8,
                    "filename": "requirements.pdf",
                    "page": 4,
                    "evidence": "A risk exists.",
                }
            ]),
            provider="test",
            model="test-model",
            status="Completed",
            source_fingerprint="a" * 64,
        )
        db.session.add(item)
        db.session.commit()

        assert item.sources[0]["filename"] == "requirements.pdf"
        assert item.sources[0]["page"] == 4

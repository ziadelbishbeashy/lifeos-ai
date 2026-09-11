"""Route tests for the Step 6D confirmation boundary."""

from types import SimpleNamespace

from database import db
from models import (
    Document,
    Project,
)


def _login(client):
    return client.post(
        "/login",
        data={
            "email": "student@example.com",
            "password": "StrongPass123!",
        },
        follow_redirects=True,
    )


def test_analysis_route_passes_confirmed_and_detected_types(
    app,
    client,
    user,
    monkeypatch,
):
    from routes import document_routes

    with app.app_context():
        project = Project(
            user_id=user,
            title="Type-aware Project",
            status="In Progress",
            priority="Medium",
        )

        document = Document(
            project=project,
            filename="paper.pdf",
            file_path="stored/paper.pdf",
            extracted_text="Readable research content.",
        )

        db.session.add_all(
            [
                project,
                document,
            ]
        )
        db.session.commit()

        document_id = document.id

    captured = {}

    def fake_analyse(**kwargs):
        captured.update(
            kwargs
        )

        return SimpleNamespace(
            reused_existing=False,
        )

    monkeypatch.setattr(
        document_routes,
        "analyse_owned_document",
        fake_analyse,
    )

    _login(
        client
    )

    response = client.post(
        f"/documents/{document_id}/analyse",
        data={
            "confirmed_document_type": "research_paper",
            "detected_document_type": "research_paper",
            "detection_confidence": "high",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert captured["confirmed_document_type"] == "research_paper"
    assert captured["detected_document_type"] == "research_paper"
    assert captured["detection_confidence"] == "high"


def test_analysis_route_requires_detection_first(
    app,
    client,
    user,
    monkeypatch,
):
    from routes import document_routes

    called = {
        "analysis": False,
    }

    def fake_analyse(**kwargs):
        called["analysis"] = True

    monkeypatch.setattr(
        document_routes,
        "analyse_owned_document",
        fake_analyse,
    )

    _login(
        client
    )

    response = client.post(
        "/documents/999/analyse",
        data={
            "confirmed_document_type": "research_paper",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert called["analysis"] is False

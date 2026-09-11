"""Step 13E/F document comparison route tests."""

from types import SimpleNamespace

from database import db
from models import (
    Document,
    DocumentComparison,
    Project,
)
from routes import document_routes


def _login(client):
    return client.post(
        "/login",
        data={
            "email": "student@example.com",
            "password": "StrongPass123!",
        },
        follow_redirects=False,
    )


def _documents(user):
    project = Project(
        user_id=user,
        title="Comparison project",
    )

    document_a = Document(
        project=project,
        filename="a.pdf",
        file_path="a.pdf",
        extracted_text="A",
    )

    document_b = Document(
        project=project,
        filename="b.pdf",
        file_path="b.pdf",
        extracted_text="B",
    )

    db.session.add_all(
        [
            project,
            document_a,
            document_b,
        ]
    )
    db.session.commit()

    return document_a, document_b


def test_compare_page_lists_owned_documents(
    app,
    client,
    user,
):
    with app.app_context():
        document_a, document_b = _documents(user)
        names = {
            document_a.filename,
            document_b.filename,
        }

    _login(client)

    response = client.get(
        "/documents/compare"
    )

    assert response.status_code == 200

    html = response.get_data(
        as_text=True
    )

    for name in names:
        assert name in html

    assert "Compare two documents" in html


def test_compare_post_redirects_to_saved_result(
    app,
    client,
    user,
    monkeypatch,
):
    with app.app_context():
        document_a, document_b = _documents(user)

        comparison = DocumentComparison(
            user_id=user,
            document_a_id=document_a.id,
            document_b_id=document_b.id,
            provider="test",
            model="test-model",
            status="Completed",
            source_fingerprint="a" * 64,
            summary="Verified.",
            findings_json="[]",
        )
        db.session.add(comparison)
        db.session.commit()

        document_a_id = document_a.id
        document_b_id = document_b.id
        comparison_id = comparison.id

    monkeypatch.setattr(
        document_routes,
        "compare_owned_documents",
        lambda **kwargs: SimpleNamespace(
            comparison=SimpleNamespace(
                id=comparison_id
            ),
            reused_existing=False,
            rejected_findings=0,
        ),
    )

    _login(client)

    response = client.post(
        "/documents/compare",
        data={
            "document_a_id": document_a_id,
            "document_b_id": document_b_id,
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        f"/documents/comparisons/{comparison_id}"
    )


def test_foreign_comparison_details_returns_404(
    app,
    client,
    user,
):
    from models import User

    with app.app_context():
        outsider = User(
            name="Outsider",
            email="outsider@example.com",
        )
        outsider.set_password(
            "StrongPass123!"
        )

        project = Project(
            owner=outsider,
            title="Private",
        )

        document_a = Document(
            project=project,
            filename="private-a.pdf",
            file_path="private-a.pdf",
            extracted_text="A",
        )

        document_b = Document(
            project=project,
            filename="private-b.pdf",
            file_path="private-b.pdf",
            extracted_text="B",
        )

        db.session.add_all(
            [
                outsider,
                project,
                document_a,
                document_b,
            ]
        )
        db.session.flush()

        comparison = DocumentComparison(
            user_id=outsider.id,
            document_a_id=document_a.id,
            document_b_id=document_b.id,
            provider="test",
            model="test-model",
            status="Completed",
            source_fingerprint="b" * 64,
            summary="Private.",
            findings_json="[]",
        )
        db.session.add(comparison)
        db.session.commit()

        comparison_id = comparison.id

    _login(client)

    response = client.get(
        f"/documents/comparisons/{comparison_id}"
    )

    assert response.status_code == 404

"""I21 Academic Schedule — module assessment API/service regression tests."""

from datetime import date, timedelta

from database import db
from models import ModuleAssessment, User
from services.module_service import create_module


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "student@example.com",
            "password": "StrongPass123!",
        },
    )
    assert response.status_code == 200


def _module(app, user_id: int, title: str = "Machine Learning") -> int:
    with app.app_context():
        return create_module(user_id=user_id, title=title).id


def test_assessment_api_requires_authentication(app, client, user):
    module_id = _module(app, user)
    response = client.get(f"/api/v1/modules/{module_id}/assessments")
    assert response.status_code == 401


def test_create_module_assessment_returns_deterministic_schedule_facts(app, client, user):
    _login(client)
    module_id = _module(app, user)
    target = date.today() + timedelta(days=3)

    response = client.post(
        f"/api/v1/modules/{module_id}/assessments",
        json={
            "title": "Classification Quiz",
            "assessment_type": "Quiz",
            "assessment_date": target.isoformat(),
            "assessment_time": "10:30",
            "weight_percent": 10,
            "topics": "Logistic Regression, KNN, Precision and Recall",
            "estimated_study_minutes": 150,
            "notes": "Review lecture 4 before quiz.",
        },
    )

    assert response.status_code == 201
    assessment = response.get_json()["item"]
    assert assessment["title"] == "Classification Quiz"
    assert assessment["assessment_type"] == "Quiz"
    assert assessment["assessment_date"] == target.isoformat()
    assert assessment["target_date"] == target.isoformat()
    assert assessment["weight_percent"] == 10.0
    assert assessment["estimated_study_minutes"] == 150
    assert assessment["days_until"] == 3
    assert assessment["timing_label"] == "This week"

    with app.app_context():
        stored = ModuleAssessment.query.filter_by(module_id=module_id).one()
        assert stored.title == "Classification Quiz"


def test_assignment_prefers_due_date_as_target_date(app, client, user):
    _login(client)
    module_id = _module(app, user)
    due = date.today() + timedelta(days=8)

    response = client.post(
        f"/api/v1/modules/{module_id}/assessments",
        json={
            "title": "Database Coursework",
            "assessment_type": "Assignment",
            "due_date": due.isoformat(),
            "weight_percent": "25.5",
        },
    )

    assert response.status_code == 201
    assessment = response.get_json()["item"]
    assert assessment["target_date"] == due.isoformat()
    assert assessment["days_until"] == 8
    assert assessment["weight_percent"] == 25.5


def test_list_module_assessments_and_module_detail_include_assessments(app, client, user):
    _login(client)
    module_id = _module(app, user)
    first = date.today() + timedelta(days=5)
    second = date.today() + timedelta(days=30)

    for title, kind, target in (
        ("Quiz 1", "Quiz", first),
        ("Final Exam", "Final", second),
    ):
        response = client.post(
            f"/api/v1/modules/{module_id}/assessments",
            json={
                "title": title,
                "assessment_type": kind,
                "assessment_date": target.isoformat(),
            },
        )
        assert response.status_code == 201

    response = client.get(f"/api/v1/modules/{module_id}/assessments")
    assert response.status_code == 200
    assessments = response.get_json()["items"]
    assert [item["title"] for item in assessments] == ["Quiz 1", "Final Exam"]

    detail = client.get(f"/api/v1/modules/{module_id}")
    assert detail.status_code == 200
    item = detail.get_json()["item"]
    assert item["counts"]["assessments"] == 2
    assert len(item["assessments"]) == 2


def test_assessment_rejects_invalid_weight_without_persisting(app, client, user):
    _login(client)
    module_id = _module(app, user)

    response = client.post(
        f"/api/v1/modules/{module_id}/assessments",
        json={
            "title": "Impossible Quiz",
            "assessment_type": "Quiz",
            "weight_percent": 150,
        },
    )

    assert response.status_code == 400
    assert "weight_percent" in response.get_json()["message"]
    with app.app_context():
        assert ModuleAssessment.query.filter_by(module_id=module_id).count() == 0


def test_assessment_rejects_unknown_type(app, client, user):
    _login(client)
    module_id = _module(app, user)
    response = client.post(
        f"/api/v1/modules/{module_id}/assessments",
        json={"title": "Mystery", "assessment_type": "Surprise"},
    )
    assert response.status_code == 400


def test_update_module_assessment(app, client, user):
    _login(client)
    module_id = _module(app, user)
    created = client.post(
        f"/api/v1/modules/{module_id}/assessments",
        json={"title": "Quiz", "assessment_type": "Quiz", "weight_percent": 10},
    )
    assessment_id = created.get_json()["item"]["id"]

    response = client.patch(
        f"/api/v1/modules/{module_id}/assessments/{assessment_id}",
        json={"title": "Quiz 1", "weight_percent": 15, "status": "Completed"},
    )

    assert response.status_code == 200
    assessment = response.get_json()["item"]
    assert assessment["title"] == "Quiz 1"
    assert assessment["weight_percent"] == 15.0
    assert assessment["status"] == "Completed"
    assert assessment["timing_label"] == "Completed"


def test_assessment_cannot_be_updated_through_wrong_module(app, client, user):
    _login(client)
    module_a = _module(app, user, "Machine Learning")
    module_b = _module(app, user, "Operating Systems")
    created = client.post(
        f"/api/v1/modules/{module_a}/assessments",
        json={"title": "ML Quiz", "assessment_type": "Quiz"},
    )
    assessment_id = created.get_json()["item"]["id"]

    response = client.patch(
        f"/api/v1/modules/{module_b}/assessments/{assessment_id}",
        json={"title": "Wrong parent"},
    )
    assert response.status_code == 404

    with app.app_context():
        assert db.session.get(ModuleAssessment, assessment_id).title == "ML Quiz"


def test_user_cannot_access_another_users_assessments(app, client, user):
    _login(client)
    with app.app_context():
        other = User(name="Other Student", email="other-i21@example.com")
        other.set_password("StrongPass123!")
        db.session.add(other)
        db.session.commit()
        other_module_id = create_module(user_id=other.id, title="Private Physics").id

    response = client.get(f"/api/v1/modules/{other_module_id}/assessments")
    assert response.status_code == 404


def test_delete_module_assessment(app, client, user):
    _login(client)
    module_id = _module(app, user)
    created = client.post(
        f"/api/v1/modules/{module_id}/assessments",
        json={"title": "Lab Assessment", "assessment_type": "Lab"},
    )
    assessment_id = created.get_json()["item"]["id"]

    response = client.delete(
        f"/api/v1/modules/{module_id}/assessments/{assessment_id}"
    )
    assert response.status_code == 200
    assert response.get_json()["deleted"] is True

    with app.app_context():
        assert db.session.get(ModuleAssessment, assessment_id) is None

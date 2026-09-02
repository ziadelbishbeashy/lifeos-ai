"""I20 adaptive experience profiles: one LifeOS core, configurable defaults."""
from database import db
from models import User, UserExperienceProfile
from services.experience_profile_service import experience_context_for_ai, save_experience_profile


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "StrongPass123!"},
    )
    assert response.status_code == 200
    return response.get_json()


def test_existing_user_session_exposes_unconfigured_profile_without_writing(app, client, user):
    with app.app_context():
        assert UserExperienceProfile.query.filter_by(user_id=user).count() == 0

    payload = _login(client)
    experience = payload["user"]["experience"]
    assert experience["primary_experience"] is None
    assert experience["onboarding_completed"] is False
    assert len(experience["available_experiences"]) == 4

    session = client.get("/api/v1/session").get_json()
    assert session["user"]["experience"]["onboarding_completed"] is False
    with app.app_context():
        assert UserExperienceProfile.query.filter_by(user_id=user).count() == 0


def test_profile_update_supports_primary_plus_additional_experiences(app, client, user):
    _login(client)
    response = client.patch(
        "/api/v1/experience/profile",
        json={
            "primary_experience": "professional",
            "enabled_experiences": ["professional", "self_learning"],
        },
    )
    assert response.status_code == 200
    experience = response.get_json()["experience"]
    assert experience["primary_experience"] == "professional"
    assert experience["enabled_experiences"] == ["professional", "self_learning"]
    assert experience["onboarding_completed"] is True
    # Extra self-learning enables learning UI without changing the primary work experience.
    assert experience["ui"]["modules_visible"] is True
    assert experience["ui"]["module_label"] == "Learning"
    assert experience["primary"]["label"] == "Professional"

    session = client.get("/api/v1/session").get_json()
    assert session["user"]["experience"]["primary_experience"] == "professional"


def test_profile_update_rejects_unknown_experience(client, user):
    _login(client)
    response = client.patch(
        "/api/v1/experience/profile",
        json={"primary_experience": "wizard", "enabled_experiences": ["wizard"]},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "validation_error"


def test_registration_can_complete_experience_onboarding(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "New Student",
            "email": "new-student@example.com",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
            "primary_experience": "student",
        },
    )
    assert response.status_code == 201
    experience = response.get_json()["user"]["experience"]
    assert experience["primary_experience"] == "student"
    assert experience["enabled_experiences"] == ["student"]
    assert experience["onboarding_completed"] is True
    assert experience["ui"]["modules_visible"] is True
    assert experience["ui"]["module_label"] == "Modules"


def test_experience_context_is_explicit_user_preference(app, user):
    with app.app_context():
        account = db.session.get(User, user)
        save_experience_profile(
            user=account,
            primary_experience="self_learning",
            enabled_experiences=["self_learning", "personal"],
        )
        context = experience_context_for_ai(user)
        assert context == {
            "primary_experience": "self_learning",
            "enabled_experiences": ["self_learning", "personal"],
            "label": "Self-Learning",
            "home_focus": "learning_and_execution",
            "is_configured": True,
        }


def test_experience_profile_api_requires_authentication(client):
    response = client.get("/api/v1/experience/profile")
    assert response.status_code == 401
    assert response.get_json()["error"] == "authentication_required"

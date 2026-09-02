"""Experience-profile API: one shared LifeOS, adaptive defaults."""
from __future__ import annotations

from flask import Blueprint, jsonify
from flask_login import current_user

from lifeos.api.v1.common import api_auth_required, json_body, persistence_error, validation_error
from services.experience_profile_service import (
    EXPERIENCE_DEFINITIONS,
    EXPERIENCE_KEYS,
    ExperienceProfilePersistenceError,
    ExperienceProfileValidationError,
    save_experience_profile,
    serialize_experience_profile,
    user_experience_payload,
)

experience_api_bp = Blueprint("experience_api", __name__, url_prefix="/api/v1/experience")




@experience_api_bp.get("/options")
def experience_options():
    return jsonify({"experiences": [dict(EXPERIENCE_DEFINITIONS[key]) for key in EXPERIENCE_KEYS]})


@experience_api_bp.get("/profile")
@api_auth_required
def get_profile():
    return jsonify({"experience": user_experience_payload(current_user)})


@experience_api_bp.patch("/profile")
@api_auth_required
def update_profile():
    payload = json_body()
    try:
        profile = save_experience_profile(
            user=current_user,
            primary_experience=payload.get("primary_experience"),
            enabled_experiences=payload.get("enabled_experiences"),
            complete_onboarding=True,
        )
    except ExperienceProfileValidationError as error:
        return validation_error(str(error))
    except ExperienceProfilePersistenceError as error:
        return persistence_error(str(error))
    return jsonify({"experience": serialize_experience_profile(profile)})

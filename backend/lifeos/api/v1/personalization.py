"""Private V-SPACE personalization profile API."""
from __future__ import annotations

from flask import Blueprint, jsonify
from flask_login import current_user

from lifeos.api.v1.common import api_auth_required, json_body, persistence_error, validation_error
from services.personalization_profile_service import (
    PersonalizationPersistenceError,
    PersonalizationValidationError,
    clear_profile,
    defer_profile,
    profile_for_user,
    save_profile,
    serialize_profile,
)

personalization_api_bp = Blueprint("personalization_api", __name__, url_prefix="/api/v1/personalization")


@personalization_api_bp.get("")
@api_auth_required
def get_personalization():
    return jsonify({"personalization": serialize_profile(profile_for_user(current_user))})


@personalization_api_bp.patch("")
@api_auth_required
def update_personalization():
    try:
        profile = save_profile(user=current_user, payload=json_body())
    except PersonalizationValidationError as error:
        return validation_error(str(error))
    except PersonalizationPersistenceError as error:
        return persistence_error(str(error))
    return jsonify({"personalization": serialize_profile(profile)})


@personalization_api_bp.post("/defer")
@api_auth_required
def defer_personalization():
    try:
        profile = defer_profile(user=current_user)
    except PersonalizationPersistenceError as error:
        return persistence_error(str(error))
    return jsonify({"personalization": serialize_profile(profile)})


@personalization_api_bp.delete("")
@api_auth_required
def clear_personalization():
    try:
        profile = clear_profile(user=current_user)
    except PersonalizationPersistenceError as error:
        return persistence_error(str(error))
    return jsonify({"personalization": serialize_profile(profile), "cleared": True})

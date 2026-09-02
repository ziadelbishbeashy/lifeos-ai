"""Adaptive user-experience profiles for one shared LifeOS product.

Profiles change defaults, labels and recommendation context only. They do not
fork the application, duplicate domain models, or remove authorization checks.
All underlying LifeOS capabilities remain the same shared services.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy.exc import SQLAlchemyError

from database import db
from models import User, UserExperienceProfile

EXPERIENCE_KEYS = ("student", "self_learning", "professional", "personal")

EXPERIENCE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "student": {
        "key": "student",
        "label": "Student",
        "short_label": "Study",
        "description": "Classes, modules, deadlines, study planning and tutoring.",
        "workspace_label": "Student workspace",
        "module_label": "Modules",
        "modules_visible": True,
        "home_focus": "study_and_execution",
        "ask_prompts": [
            "What should I study next?",
            "Help me organize my week around my deadlines.",
            "Which module needs the most attention?",
            "Teach me the topic I should focus on next.",
        ],
    },
    "self_learning": {
        "key": "self_learning",
        "label": "Self-Learning",
        "short_label": "Learning",
        "description": "Build skills, learn independently, practice and track progress.",
        "workspace_label": "Learning workspace",
        "module_label": "Learning",
        "modules_visible": True,
        "home_focus": "learning_and_execution",
        "ask_prompts": [
            "What should I learn next?",
            "Build me a useful study session for today.",
            "What topic should I practice more?",
            "Teach me this step by step.",
        ],
    },
    "professional": {
        "key": "professional",
        "label": "Professional",
        "short_label": "Work",
        "description": "Projects, deadlines, documents, focus and work intelligence.",
        "workspace_label": "Work workspace",
        "module_label": "Modules",
        "modules_visible": False,
        "home_focus": "projects_and_execution",
        "ask_prompts": [
            "What should I focus on today?",
            "Which project is most at risk?",
            "What changed in my workspace this week?",
            "Help me move my highest-priority project forward.",
        ],
    },
    "personal": {
        "key": "personal",
        "label": "Personal",
        "short_label": "Personal",
        "description": "Tasks, personal projects, notes, documents and daily organization.",
        "workspace_label": "Personal workspace",
        "module_label": "Modules",
        "modules_visible": False,
        "home_focus": "personal_execution",
        "ask_prompts": [
            "What should I focus on today?",
            "Help me organize my week.",
            "Which tasks need attention first?",
            "What have I left unfinished?",
        ],
    },
}

# Extra experiences only add emphasis/capabilities. The primary experience is
# always included automatically.
MAX_ENABLED_EXPERIENCES = len(EXPERIENCE_KEYS)


class ExperienceProfileValidationError(ValueError):
    pass


class ExperienceProfilePersistenceError(RuntimeError):
    pass


def _normalise_key(value: Any, *, allow_empty: bool = False) -> str | None:
    key = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "selflearner": "self_learning",
        "self_learner": "self_learning",
        "learner": "self_learning",
        "work": "professional",
        "professional_work": "professional",
    }
    key = aliases.get(key, key)
    if not key and allow_empty:
        return None
    if key not in EXPERIENCE_DEFINITIONS:
        raise ExperienceProfileValidationError("Choose a supported LifeOS experience.")
    return key


def validate_experience_key(value: Any) -> str:
    """Validate and normalize one public experience key."""
    result = _normalise_key(value)
    assert result is not None
    return result


def _normalise_enabled(values: Any, *, primary: str | None) -> list[str]:
    if values is None:
        raw: Iterable[Any] = ()
    elif isinstance(values, (list, tuple, set)):
        raw = values
    else:
        raise ExperienceProfileValidationError("Enabled experiences must be a list.")

    result: list[str] = []
    for value in raw:
        key = _normalise_key(value)
        if key not in result:
            result.append(key)
    if primary and primary not in result:
        result.insert(0, primary)
    if len(result) > MAX_ENABLED_EXPERIENCES:
        raise ExperienceProfileValidationError("Too many experiences were selected.")
    return result


def profile_for_user(user_or_id: User | int) -> UserExperienceProfile | None:
    if hasattr(user_or_id, "id"):
        return getattr(user_or_id, "experience_profile", None)
    return UserExperienceProfile.query.filter_by(user_id=int(user_or_id)).first()


def get_or_create_experience_profile(user: User) -> UserExperienceProfile:
    profile = user.experience_profile
    if profile is not None:
        return profile
    profile = UserExperienceProfile(user_id=int(user.id))
    db.session.add(profile)
    db.session.flush()
    return profile


def experience_definition(key: str | None) -> dict[str, Any] | None:
    if not key:
        return None
    definition = EXPERIENCE_DEFINITIONS.get(str(key))
    return dict(definition) if definition else None


def serialize_experience_profile(profile: UserExperienceProfile | None) -> dict[str, Any]:
    primary = str(profile.primary_experience or "").strip() if profile else ""
    primary = primary if primary in EXPERIENCE_DEFINITIONS else None
    enabled = profile.enabled_experiences() if profile else []
    enabled = [item for item in enabled if item in EXPERIENCE_DEFINITIONS]
    if primary and primary not in enabled:
        enabled.insert(0, primary)
    definition = experience_definition(primary)

    enabled_definitions = [EXPERIENCE_DEFINITIONS[key] for key in enabled if key in EXPERIENCE_DEFINITIONS]
    modules_visible = any(bool(item.get("modules_visible")) for item in enabled_definitions)
    if "student" in enabled:
        module_label = "Modules"
    elif "self_learning" in enabled:
        module_label = "Learning"
    else:
        module_label = definition["module_label"] if definition else "Modules"
    prompts: list[str] = []
    for item in ([definition] if definition else []) + enabled_definitions:
        if not item:
            continue
        for prompt in item.get("ask_prompts") or []:
            if prompt not in prompts:
                prompts.append(prompt)

    # Keep one stable product navigation. Only optional emphasis changes.
    ui = {
        "workspace_label": definition["workspace_label"] if definition else "Personal workspace",
        "module_label": module_label,
        "modules_visible": modules_visible,
        "home_focus": definition["home_focus"] if definition else "general",
        "ask_prompts": prompts[:8],
    }
    return {
        "primary_experience": primary,
        "enabled_experiences": enabled,
        "onboarding_completed": bool(profile and profile.onboarding_completed and primary),
        "primary": definition,
        "ui": ui,
        "available_experiences": [dict(EXPERIENCE_DEFINITIONS[key]) for key in EXPERIENCE_KEYS],
    }


def user_experience_payload(user: User) -> dict[str, Any]:
    return serialize_experience_profile(profile_for_user(user))


def save_experience_profile(
    *,
    user: User,
    primary_experience: Any,
    enabled_experiences: Any = None,
    complete_onboarding: bool = True,
) -> UserExperienceProfile:
    primary = _normalise_key(primary_experience)
    enabled = _normalise_enabled(enabled_experiences, primary=primary)
    profile = get_or_create_experience_profile(user)
    profile.primary_experience = primary
    profile.set_enabled_experiences(enabled)
    if complete_onboarding:
        profile.onboarding_completed = True
    try:
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise ExperienceProfilePersistenceError("LifeOS could not save your experience settings.") from error
    return profile


def create_registration_profile(*, user: User, primary_experience: Any) -> UserExperienceProfile:
    """Persist the onboarding choice immediately after successful registration."""
    return save_experience_profile(
        user=user,
        primary_experience=primary_experience,
        enabled_experiences=[primary_experience],
        complete_onboarding=True,
    )


def experience_context_for_ai(owner_id: int) -> dict[str, Any]:
    """Small non-sensitive preference context for UI/reasoning personalization.

    This is preference context only. It must never substitute for factual
    workspace evidence (deadlines, grades, tasks, project state, etc.).
    """
    profile = profile_for_user(int(owner_id))
    payload = serialize_experience_profile(profile)
    primary = payload.get("primary") or {}
    return {
        "primary_experience": payload.get("primary_experience"),
        "enabled_experiences": list(payload.get("enabled_experiences") or []),
        "label": primary.get("label"),
        "home_focus": (payload.get("ui") or {}).get("home_focus"),
        "is_configured": bool(payload.get("onboarding_completed")),
    }

"""Application configuration for LifeOS.

The project uses explicit configuration classes so local development, automated
checks, and public deployment do not accidentally share unsafe settings.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

from database import get_database_uri


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable safely."""

    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int, minimum: int | None = None) -> int:
    """Read an integer environment variable without breaking app import."""

    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


class BaseConfig:
    """Settings shared by every LifeOS environment."""

    ENV_NAME = "base"
    SECRET_KEY = os.getenv("SECRET_KEY", "development-only-change-me")
    SQLALCHEMY_DATABASE_URI = get_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_NAME = "lifeos_session"
    PERMANENT_SESSION_LIFETIME = timedelta(days=14)

    WTF_CSRF_ENABLED = True
    WTF_CSRF_CHECK_DEFAULT = True
    WTF_CSRF_TIME_LIMIT = 4 * 60 * 60
    WTF_CSRF_SSL_STRICT = True

    MAX_CONTENT_LENGTH = env_int(
        "MAX_UPLOAD_SIZE_MB",
        25,
        minimum=1,
    ) * 1024 * 1024

    TEMPLATES_AUTO_RELOAD = False
    AUTO_CREATE_DB = False
    ENABLE_EMAIL_SCHEDULER = False
    SECURITY_HEADERS_ENABLED = True

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")
    LOCAL_STORAGE_ROOT = os.getenv(
        "LOCAL_STORAGE_ROOT",
        str(BASE_DIR / "instance" / "storage"),
    )
    JOB_BACKEND = os.getenv("JOB_BACKEND", "inline")
    EMAIL_SCHEDULER_INTERVAL_MINUTES = env_int(
        "EMAIL_SCHEDULER_INTERVAL_MINUTES",
        60,
        minimum=1,
    )
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:5000")
    TRUST_PROXY_HEADERS = env_bool("TRUST_PROXY_HEADERS", False)
    MAIL_TIMEOUT_SECONDS = env_int("MAIL_TIMEOUT_SECONDS", 20, minimum=1)


class DevelopmentConfig(BaseConfig):
    """Local developer configuration."""

    ENV_NAME = "development"
    DEBUG = env_bool("FLASK_DEBUG", False)
    TEMPLATES_AUTO_RELOAD = True
    AUTO_CREATE_DB = env_bool("AUTO_CREATE_DB", True)
    ENABLE_EMAIL_SCHEDULER = env_bool("ENABLE_EMAIL_SCHEDULER", False)

    SESSION_COOKIE_SECURE = env_bool("COOKIE_SECURE", False)
    REMEMBER_COOKIE_SECURE = env_bool("COOKIE_SECURE", False)
    WTF_CSRF_SSL_STRICT = env_bool("COOKIE_SECURE", False)


class TestingConfig(BaseConfig):
    """Fast, isolated configuration for automated tests."""

    ENV_NAME = "testing"
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "TEST_DATABASE_URL",
        "sqlite:///:memory:",
    )
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    ENABLE_EMAIL_SCHEDULER = False
    AUTO_CREATE_DB = False
    WTF_CSRF_ENABLED = False
    JOB_BACKEND = "memory"
    LOG_LEVEL = "WARNING"


class ProductionConfig(BaseConfig):
    """Safe defaults for a public deployment."""

    ENV_NAME = "production"
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    TEMPLATES_AUTO_RELOAD = False
    ENABLE_EMAIL_SCHEDULER = False
    AUTO_CREATE_DB = False
    TRUST_PROXY_HEADERS = True
    PREFERRED_URL_SCHEME = "https"


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config_name() -> str:
    """Return the requested environment, falling back to development."""

    requested = (
        os.getenv("LIFEOS_ENV")
        or os.getenv("APP_ENV")
        or "development"
    ).strip().lower()

    return requested if requested in CONFIG_BY_NAME else "development"


def validate_config(app) -> None:
    """Fail early when a public deployment uses unsafe configuration."""

    if app.config.get("TESTING"):
        return

    if app.config.get("ENV_NAME") != "production":
        return

    secret_key = app.config.get("SECRET_KEY", "")
    unsafe_keys = {
        "",
        "development-only-change-me",
        "development-only-secret-key",
    }

    if secret_key in unsafe_keys or len(secret_key) < 32:
        raise RuntimeError(
            "Production requires a strong SECRET_KEY of at least 32 characters."
        )

    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("Production requires a database connection string.")

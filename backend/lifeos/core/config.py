"""Environment configuration for LifeOS Foundation V2."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.engine import make_url

from dotenv import load_dotenv

from lifeos.core.database import get_database_uri, is_postgres_uri


BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int, minimum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def env_csv(name: str) -> tuple[str, ...]:
    value = os.getenv(name, "")
    return tuple(item.strip() for item in value.split(",") if item.strip())


def env_float(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


class BaseConfig:
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
    REMEMBER_COOKIE_DURATION = timedelta(days=env_int("REMEMBER_COOKIE_DAYS", 14, minimum=1))

    WTF_CSRF_ENABLED = True
    WTF_CSRF_CHECK_DEFAULT = True
    WTF_CSRF_TIME_LIMIT = 4 * 60 * 60
    WTF_CSRF_SSL_STRICT = True

    MAX_CONTENT_LENGTH = env_int("MAX_UPLOAD_SIZE_MB", 25, minimum=1) * 1024 * 1024
    MAX_API_JSON_BYTES = env_int("MAX_API_JSON_KB", 256, minimum=16) * 1024

    # Step 20 — predictable resource and provider-cost boundaries.
    MAX_PDF_PAGES = env_int("MAX_PDF_PAGES", 300, minimum=1)
    MAX_EXTRACTED_TEXT_CHARACTERS = env_int(
        "MAX_EXTRACTED_TEXT_CHARACTERS", 200_000, minimum=10_000
    )
    MAX_CHUNKS_PER_DOCUMENT = env_int("MAX_CHUNKS_PER_DOCUMENT", 250, minimum=10)
    MAX_SCOPE_DOCUMENTS = env_int("MAX_SCOPE_DOCUMENTS", 50, minimum=1)
    MAX_RETRIEVAL_RESULTS = env_int("MAX_RETRIEVAL_RESULTS", 12, minimum=1)
    MAX_RAG_CONTEXT_CHARACTERS = env_int(
        "MAX_RAG_CONTEXT_CHARACTERS", 20_000, minimum=500
    )
    MAX_AI_PROMPT_CHARACTERS = env_int(
        "MAX_AI_PROMPT_CHARACTERS", 120_000, minimum=2_000
    )
    AI_MAX_GENERATION_CALLS_PER_REQUEST = env_int(
        "AI_MAX_GENERATION_CALLS_PER_REQUEST", 4, minimum=1
    )
    MAX_EMBEDDING_BATCH_SIZE = env_int(
        "MAX_EMBEDDING_BATCH_SIZE", 50, minimum=1
    )
    AI_MAX_EMBEDDING_CALLS_PER_REQUEST = env_int(
        "AI_MAX_EMBEDDING_CALLS_PER_REQUEST", 12, minimum=1
    )
    AI_MAX_EMBEDDING_CHARACTERS_PER_REQUEST = env_int(
        "AI_MAX_EMBEDDING_CHARACTERS_PER_REQUEST", 120_000, minimum=1_000
    )

    TEMPLATES_AUTO_RELOAD = False
    AUTO_CREATE_DB = False
    ENABLE_EMAIL_SCHEDULER = False
    # I17 preparation. Keep autonomous automation execution disabled until the
    # preparation test gate is explicitly completed. Definitions/previews are
    # still available through the authenticated API.
    ENABLE_LIFEOS_AUTOMATIONS = env_bool("ENABLE_LIFEOS_AUTOMATIONS", False)
    LIFEOS_AUTOMATION_POLL_SECONDS = env_int("LIFEOS_AUTOMATION_POLL_SECONDS", 60, minimum=60)
    LIFEOS_DEFAULT_TIMEZONE = os.getenv("LIFEOS_DEFAULT_TIMEZONE", "UTC")
    SECURITY_HEADERS_ENABLED = True

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")
    LOCAL_STORAGE_ROOT = os.getenv(
        "LOCAL_STORAGE_ROOT",
        str(BACKEND_DIR / "instance" / "storage"),
    )
    JOB_BACKEND = os.getenv("JOB_BACKEND", "inline")

    # Step 15 OCR. Disabled by default so ordinary native-text PDFs keep the
    # same zero-dependency path. Enable Tesseract explicitly per environment.
    OCR_PROVIDER = os.getenv("OCR_PROVIDER", "disabled")
    OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "eng")
    OCR_TESSERACT_CMD = os.getenv("OCR_TESSERACT_CMD")
    OCR_TESSERACT_PSM_MODES = os.getenv("OCR_TESSERACT_PSM_MODES", "3,6,11")
    OCR_EASYOCR_ENABLED = env_bool("OCR_EASYOCR_ENABLED", False)
    OCR_EASYOCR_LANGUAGES = os.getenv("OCR_EASYOCR_LANGUAGES", "")
    OCR_EASYOCR_GPU = env_bool("OCR_EASYOCR_GPU", False)
    OCR_EASYOCR_MODEL_DIR = os.getenv("OCR_EASYOCR_MODEL_DIR")
    OCR_EASYOCR_DOWNLOAD_ENABLED = env_bool("OCR_EASYOCR_DOWNLOAD_ENABLED", True)
    OCR_RENDER_DPI = env_int("OCR_RENDER_DPI", 300, minimum=72)
    OCR_LOW_CONFIDENCE_THRESHOLD = env_float(
        "OCR_LOW_CONFIDENCE_THRESHOLD",
        0.70,
        minimum=0.0,
        maximum=1.0,
    )
    OCR_AUTO_ENQUEUE = env_bool("OCR_AUTO_ENQUEUE", False)
    # Step 15E.1: optional provider-neutral OpenCV cleanup before OCR.
    OCR_PREPROCESSING_ENABLED = env_bool("OCR_PREPROCESSING_ENABLED", False)
    OCR_PREPROCESSING_MODE = os.getenv("OCR_PREPROCESSING_MODE", "auto")
    EMAIL_SCHEDULER_INTERVAL_MINUTES = env_int(
        "EMAIL_SCHEDULER_INTERVAL_MINUTES", 60, minimum=1
    )
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:5000")
    ALLOWED_HOSTS = env_csv("ALLOWED_HOSTS")
    # Exact browser origins that a trusted local/reverse proxy may preserve while
    # forwarding requests to Flask. This does not enable CORS and does not bypass
    # Fetch Metadata or CSRF checks.
    TRUSTED_API_ORIGINS = env_csv("TRUSTED_API_ORIGINS")
    TRUST_PROXY_HEADERS = env_bool("TRUST_PROXY_HEADERS", False)
    MAIL_TIMEOUT_SECONDS = env_int("MAIL_TIMEOUT_SECONDS", 20, minimum=1)
    REQUIRE_POSTGRES_IN_PRODUCTION = env_bool(
        "REQUIRE_POSTGRES_IN_PRODUCTION", True
    )
    REQUIRE_DATABASE_TLS_IN_PRODUCTION = env_bool(
        "REQUIRE_DATABASE_TLS_IN_PRODUCTION", True
    )
    ALLOW_LEGACY_PROJECT_AUTO_CLAIM = env_bool(
        "ALLOW_LEGACY_PROJECT_AUTO_CLAIM", True
    )


class DevelopmentConfig(BaseConfig):
    ENV_NAME = "development"
    # Vite serves React on :5173 and proxies /api to Flask on :5000. The browser
    # Origin is preserved by the proxy, so explicitly trust only the two standard
    # local development origins unless the developer overrides the env setting.
    TRUSTED_API_ORIGINS = env_csv("TRUSTED_API_ORIGINS") or (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    DEBUG = env_bool("FLASK_DEBUG", False)
    TEMPLATES_AUTO_RELOAD = True
    AUTO_CREATE_DB = env_bool("AUTO_CREATE_DB", True)
    ENABLE_EMAIL_SCHEDULER = env_bool("ENABLE_EMAIL_SCHEDULER", False)
    SESSION_COOKIE_SECURE = env_bool("COOKIE_SECURE", False)
    REMEMBER_COOKIE_SECURE = env_bool("COOKIE_SECURE", False)
    WTF_CSRF_SSL_STRICT = env_bool("COOKIE_SECURE", False)


class TestingConfig(BaseConfig):
    ENV_NAME = "testing"
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    ENABLE_EMAIL_SCHEDULER = False
    AUTO_CREATE_DB = False
    WTF_CSRF_ENABLED = False
    JOB_BACKEND = "memory"
    LOG_LEVEL = "WARNING"


class ProductionConfig(BaseConfig):
    ENV_NAME = "production"
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    TEMPLATES_AUTO_RELOAD = False
    ENABLE_EMAIL_SCHEDULER = False
    AUTO_CREATE_DB = False
    TRUST_PROXY_HEADERS = env_bool("TRUST_PROXY_HEADERS", False)
    ALLOW_LEGACY_PROJECT_AUTO_CLAIM = False
    PREFERRED_URL_SCHEME = "https"


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config_name() -> str:
    requested = (
        os.getenv("LIFEOS_ENV")
        or os.getenv("APP_ENV")
        or "development"
    ).strip().lower()
    return requested if requested in CONFIG_BY_NAME else "development"


def _database_transport_is_secure(database_uri: str) -> bool:
    """Conservatively verify encrypted DB transport without exposing credentials."""

    try:
        url = make_url(database_uri)
    except Exception:
        return False

    driver = str(url.drivername or "").casefold()
    if driver.startswith("postgresql"):
        sslmode = str(url.query.get("sslmode") or "").casefold()
        return sslmode in {"require", "verify-ca", "verify-full"}

    if driver.startswith("mssql"):
        odbc_connect = str(url.query.get("odbc_connect") or "").casefold().replace(" ", "")
        encrypted = "encrypt=yes" in odbc_connect or "encrypt=mandatory" in odbc_connect or "encrypt=strict" in odbc_connect
        verifies_certificate = "trustservercertificate=no" in odbc_connect
        return encrypted and verifies_certificate

    # SQLite/other local-only transports are not accepted as production DBs.
    return False


def validate_config(app) -> None:
    if app.config.get("TESTING"):
        return
    if app.config.get("ENV_NAME") != "production":
        return

    secret_key = app.config.get("SECRET_KEY", "")
    if secret_key in {
        "",
        "development-only-change-me",
        "development-only-secret-key",
    } or len(secret_key) < 32:
        raise RuntimeError(
            "Production requires a strong SECRET_KEY of at least 32 characters."
        )

    if app.config.get("DEBUG"):
        raise RuntimeError("Production must run with DEBUG disabled.")
    if app.config.get("AUTO_CREATE_DB"):
        raise RuntimeError("Production must use reviewed migrations; AUTO_CREATE_DB must be false.")
    if not app.config.get("WTF_CSRF_ENABLED"):
        raise RuntimeError("Production requires CSRF protection.")
    if not app.config.get("SESSION_COOKIE_SECURE") or not app.config.get("REMEMBER_COOKIE_SECURE"):
        raise RuntimeError("Production authentication cookies must be HTTPS-only.")

    public_base_url = str(app.config.get("PUBLIC_BASE_URL") or "").strip()
    parsed_public_url = urlsplit(public_base_url)
    if parsed_public_url.scheme != "https" or not parsed_public_url.hostname:
        raise RuntimeError("Production PUBLIC_BASE_URL must be a valid HTTPS URL.")

    for trusted_origin in app.config.get("TRUSTED_API_ORIGINS") or ():
        parsed_origin = urlsplit(str(trusted_origin or "").strip())
        if (
            parsed_origin.scheme != "https"
            or not parsed_origin.hostname
            or parsed_origin.username is not None
            or parsed_origin.password is not None
            or parsed_origin.path not in {"", "/"}
            or parsed_origin.query
            or parsed_origin.fragment
        ):
            raise RuntimeError(
                "Production TRUSTED_API_ORIGINS entries must be exact HTTPS origins "
                "without credentials, paths, queries, or fragments."
            )

    database_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not database_uri:
        raise RuntimeError("Production requires a database connection string.")

    if app.config.get("REQUIRE_POSTGRES_IN_PRODUCTION") and not is_postgres_uri(
        database_uri
    ):
        raise RuntimeError(
            "Foundation V2 production requires PostgreSQL. Set DATABASE_URL to "
            "a PostgreSQL/Neon connection string, or explicitly disable "
            "REQUIRE_POSTGRES_IN_PRODUCTION during the temporary migration window."
        )

    if (
        app.config.get("REQUIRE_DATABASE_TLS_IN_PRODUCTION")
        and not _database_transport_is_secure(database_uri)
    ):
        raise RuntimeError(
            "Production database transport must use encrypted TLS. For PostgreSQL use "
            "sslmode=require/verify-ca/verify-full. For temporary SQL Server use Encrypt=yes "
            "with TrustServerCertificate=no."
        )


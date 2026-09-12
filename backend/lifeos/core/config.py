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
    SESSION_COOKIE_PATH = "/"
    SESSION_COOKIE_DOMAIN = None
    PERMANENT_SESSION_LIFETIME = timedelta(days=14)
    REMEMBER_COOKIE_DURATION = timedelta(days=env_int("REMEMBER_COOKIE_DAYS", 14, minimum=1))
    SESSION_REFRESH_EACH_REQUEST = False

    # Authentication V1. Flask's signed HttpOnly cookie carries a high-entropy
    # opaque session token while the revocable session record lives server-side.
    AUTH_SESSION_HOURS = env_int("AUTH_SESSION_HOURS", 12, minimum=1)
    AUTH_REMEMBER_SESSION_DAYS = env_int("AUTH_REMEMBER_SESSION_DAYS", 14, minimum=1)
    AUTH_SESSION_IDLE_MINUTES = env_int("AUTH_SESSION_IDLE_MINUTES", 120, minimum=15)
    AUTH_REMEMBER_IDLE_DAYS = env_int("AUTH_REMEMBER_IDLE_DAYS", 7, minimum=1)
    AUTH_SESSION_TOUCH_SECONDS = env_int("AUTH_SESSION_TOUCH_SECONDS", 300, minimum=60)
    AUTH_SENSITIVE_ACTION_MINUTES = env_int("AUTH_SENSITIVE_ACTION_MINUTES", 30, minimum=5)
    AUTH_RATE_WINDOW_MINUTES = env_int("AUTH_RATE_WINDOW_MINUTES", 15, minimum=1)
    AUTH_RATE_BLOCK_MINUTES = env_int("AUTH_RATE_BLOCK_MINUTES", 15, minimum=1)
    AUTH_RATE_MAX_ATTEMPTS = env_int("AUTH_RATE_MAX_ATTEMPTS", 8, minimum=3)
    PASSWORD_RESET_MINUTES = env_int("PASSWORD_RESET_MINUTES", 30, minimum=5)
    EMAIL_VERIFICATION_MINUTES = env_int("EMAIL_VERIFICATION_MINUTES", 60, minimum=5)
    AUTH_DEV_EXPOSE_TOKENS = env_bool("AUTH_DEV_EXPOSE_TOKENS", False)

    # Provider-neutral transactional email. Development defaults to SMTP so a
    # local Gmail/app-password setup can be used. Production validation requires
    # MAIL_PROVIDER=sender and Sender.net credentials. Credentials stay backend-only.
    MAIL_PROVIDER = os.getenv("MAIL_PROVIDER", "smtp").strip().lower()
    MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", os.getenv("SENDER_FROM_NAME", "V-SPACE"))
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = env_int("MAIL_PORT", 587, minimum=1)
    MAIL_USE_TLS = env_bool("MAIL_USE_TLS", True)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "")
    MAIL_TIMEOUT_SECONDS = env_int("MAIL_TIMEOUT_SECONDS", 20, minimum=1)

    SENDER_API_TOKEN = os.getenv("SENDER_API_TOKEN", "")
    SENDER_FROM_EMAIL = os.getenv("SENDER_FROM_EMAIL", "")
    SENDER_FROM_NAME = os.getenv("SENDER_FROM_NAME", "V-SPACE")
    SENDER_TIMEOUT_SECONDS = env_int("SENDER_TIMEOUT_SECONDS", 15, minimum=1)

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
    FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", PUBLIC_BASE_URL)
    GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    GOOGLE_OAUTH_REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "")
    GOOGLE_OAUTH_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
    ALLOWED_HOSTS = env_csv("ALLOWED_HOSTS")
    # Exact browser origins that a trusted local/reverse proxy may preserve while
    # forwarding requests to Flask. This does not enable CORS and does not bypass
    # Fetch Metadata or CSRF checks.
    TRUSTED_API_ORIGINS = env_csv("TRUSTED_API_ORIGINS")
    TRUST_PROXY_HEADERS = env_bool("TRUST_PROXY_HEADERS", False)
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
    FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://127.0.0.1:5173")
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
    # __Host- prevents a sibling subdomain from planting a competing auth cookie.
    SESSION_COOKIE_NAME = "__Host-vspace_session"
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
    if app.config.get("SESSION_COOKIE_SAMESITE") not in {"Lax", "Strict"}:
        raise RuntimeError("Production session cookies must use SameSite=Lax or Strict.")
    if not app.config.get("SESSION_COOKIE_HTTPONLY"):
        raise RuntimeError("Production session cookies must be HttpOnly.")
    if not str(app.config.get("SESSION_COOKIE_NAME") or "").startswith("__Host-"):
        raise RuntimeError("Production session cookies must use the __Host- prefix.")
    if app.config.get("SESSION_COOKIE_DOMAIN") not in (None, "") or app.config.get("SESSION_COOKIE_PATH") != "/":
        raise RuntimeError("__Host- session cookies must be host-only and use Path=/.")
    if app.config.get("AUTH_DEV_EXPOSE_TOKENS"):
        raise RuntimeError("Production must never expose authentication tokens in API responses.")

    mail_provider = str(app.config.get("MAIL_PROVIDER") or "").strip().lower()
    if mail_provider != "sender":
        raise RuntimeError(
            "Production authentication requires MAIL_PROVIDER=sender. SMTP is supported "
            "for development, but production must use Sender transactional email."
        )
    sender_api_token = str(app.config.get("SENDER_API_TOKEN") or "").strip()
    sender_from_email = str(app.config.get("SENDER_FROM_EMAIL") or "").strip()
    if not sender_api_token or not sender_from_email:
        raise RuntimeError(
            "Production authentication requires Sender transactional email: set "
            "SENDER_API_TOKEN and SENDER_FROM_EMAIL."
        )

    public_base_url = str(app.config.get("PUBLIC_BASE_URL") or "").strip()
    parsed_public_url = urlsplit(public_base_url)
    if parsed_public_url.scheme != "https" or not parsed_public_url.hostname:
        raise RuntimeError("Production PUBLIC_BASE_URL must be a valid HTTPS URL.")

    frontend_base_url = str(app.config.get("FRONTEND_BASE_URL") or "").strip()
    parsed_frontend_url = urlsplit(frontend_base_url)
    if parsed_frontend_url.scheme != "https" or not parsed_frontend_url.hostname:
        raise RuntimeError("Production FRONTEND_BASE_URL must be a valid HTTPS URL.")

    google_client_id = str(app.config.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    google_client_secret = str(app.config.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    if bool(google_client_id) != bool(google_client_secret):
        raise RuntimeError("Google OAuth requires both GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET.")
    if google_client_id:
        if app.config.get("SESSION_COOKIE_SAMESITE") != "Lax":
            raise RuntimeError("Google OAuth requires SESSION_COOKIE_SAMESITE=Lax so the signed state cookie returns on the callback.")
        google_redirect = str(app.config.get("GOOGLE_OAUTH_REDIRECT_URI") or "").strip() or (
            frontend_base_url.rstrip("/") + "/api/v1/auth/google/callback"
        )
        parsed_google_redirect = urlsplit(google_redirect)
        if parsed_google_redirect.scheme != "https" or not parsed_google_redirect.hostname:
            raise RuntimeError("Production Google OAuth redirect URI must be HTTPS.")

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


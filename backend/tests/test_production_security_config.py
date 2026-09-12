"""Fail-closed production configuration checks for backend/database security."""

from urllib.parse import quote_plus

import pytest
from flask import Flask

from lifeos.core.config import _database_transport_is_secure, validate_config


def _production_app(database_uri: str) -> Flask:
    app = Flask(__name__)
    app.config.update(
        ENV_NAME="production",
        TESTING=False,
        DEBUG=False,
        AUTO_CREATE_DB=False,
        WTF_CSRF_ENABLED=True,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_NAME="__Host-vspace_session",
        SESSION_COOKIE_DOMAIN=None,
        SESSION_COOKIE_PATH="/",
        REMEMBER_COOKIE_SECURE=True,
        AUTH_DEV_EXPOSE_TOKENS=False,
        MAIL_PROVIDER="sender",
        SENDER_API_TOKEN="sender-test-token",
        SENDER_FROM_EMAIL="security@lifeos.example",
        SENDER_FROM_NAME="V-SPACE",
        SECRET_KEY="s" * 64,
        PUBLIC_BASE_URL="https://lifeos.example",
        FRONTEND_BASE_URL="https://lifeos.example",
        GOOGLE_OAUTH_CLIENT_ID="",
        GOOGLE_OAUTH_CLIENT_SECRET="",
        GOOGLE_OAUTH_REDIRECT_URI="",
        SQLALCHEMY_DATABASE_URI=database_uri,
        REQUIRE_POSTGRES_IN_PRODUCTION=True,
        REQUIRE_DATABASE_TLS_IN_PRODUCTION=True,
    )
    return app


def test_production_rejects_postgres_without_required_tls():
    app = _production_app("postgresql+psycopg://lifeos:secret@db.example/lifeos")
    with pytest.raises(RuntimeError, match="database transport"):
        validate_config(app)


def test_production_accepts_postgres_with_required_tls():
    app = _production_app(
        "postgresql+psycopg://lifeos:secret@db.example/lifeos?sslmode=require"
    )
    validate_config(app)


def test_sql_server_security_check_requires_encryption_and_certificate_validation():
    secure = "mssql+pyodbc:///?odbc_connect=" + quote_plus(
        "DRIVER={ODBC Driver 17 for SQL Server};SERVER=db.example;DATABASE=LifeOS;"
        "UID=lifeos;PWD=secret;Encrypt=yes;TrustServerCertificate=no;"
    )
    insecure = "mssql+pyodbc:///?odbc_connect=" + quote_plus(
        "DRIVER={ODBC Driver 17 for SQL Server};SERVER=db.example;DATABASE=LifeOS;"
        "UID=lifeos;PWD=secret;Encrypt=yes;TrustServerCertificate=yes;"
    )

    assert _database_transport_is_secure(secure) is True
    assert _database_transport_is_secure(insecure) is False


def test_production_rejects_auth_token_exposure():
    app = _production_app(
        "postgresql+psycopg://lifeos:secret@db.example/lifeos?sslmode=require"
    )
    app.config["AUTH_DEV_EXPOSE_TOKENS"] = True
    with pytest.raises(RuntimeError, match="never expose authentication tokens"):
        validate_config(app)


def test_production_requires_complete_google_oauth_pair():
    app = _production_app(
        "postgresql+psycopg://lifeos:secret@db.example/lifeos?sslmode=require"
    )
    app.config["GOOGLE_OAUTH_CLIENT_ID"] = "client.apps.googleusercontent.com"
    app.config["GOOGLE_OAUTH_CLIENT_SECRET"] = ""
    with pytest.raises(RuntimeError, match="requires both"):
        validate_config(app)


def test_production_requires_sender_transactional_email_configuration():
    app = _production_app(
        "postgresql+psycopg://lifeos:secret@db.example/lifeos?sslmode=require"
    )
    app.config["SENDER_API_TOKEN"] = ""
    with pytest.raises(RuntimeError, match="Sender transactional email"):
        validate_config(app)


def test_production_rejects_smtp_mail_provider():
    app = _production_app(
        "postgresql+psycopg://lifeos:secret@db.example/lifeos?sslmode=require"
    )
    app.config["MAIL_PROVIDER"] = "smtp"
    with pytest.raises(RuntimeError, match="MAIL_PROVIDER=sender"):
        validate_config(app)

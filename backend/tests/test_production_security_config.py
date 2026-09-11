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
        REMEMBER_COOKIE_SECURE=True,
        SECRET_KEY="s" * 64,
        PUBLIC_BASE_URL="https://lifeos.example",
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

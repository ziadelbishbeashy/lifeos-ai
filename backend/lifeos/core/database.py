"""Database configuration and SQLAlchemy extension for LifeOS Foundation V2.

PostgreSQL is the preferred database for all new environments. ``DATABASE_URL``
can point to local PostgreSQL or Neon. Existing SQL Server configuration remains
available temporarily so the migration can be performed without a big-bang
cutover.
"""

from __future__ import annotations

import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy


load_dotenv()

db = SQLAlchemy()


def normalize_database_uri(value: str) -> str:
    """Normalize provider URLs to the psycopg 3 SQLAlchemy dialect."""

    url = str(value or "").strip()
    if not url:
        return ""

    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]

    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]

    return url


def _legacy_sql_server_uri() -> str:
    server = os.getenv("DB_SERVER", "localhost")
    database = os.getenv("DB_NAME", "LifeOSDB")
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    username = (os.getenv("DB_USERNAME") or "").strip()
    password = os.getenv("DB_PASSWORD") or ""

    if username:
        authentication = f"UID={username};PWD={password};"
    else:
        authentication = "Trusted_Connection=yes;"

    connection_string = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"{authentication}"
        "TrustServerCertificate=yes;"
    )

    return "mssql+pyodbc:///?odbc_connect=" + quote_plus(connection_string)


def _should_use_legacy_sql_server() -> bool:
    requested = (os.getenv("DB_BACKEND") or "").strip().lower()
    if requested in {"mssql", "sqlserver", "sql_server", "legacy_sqlserver"}:
        return True
    if requested in {"postgres", "postgresql", "neon"}:
        return False

    # Preserve existing developer machines that already have the old SQL Server
    # variables configured. New installs default to PostgreSQL.
    return bool(os.getenv("DB_SERVER") or os.getenv("DB_NAME"))


def get_database_uri() -> str:
    """Return the runtime SQLAlchemy database URI.

    Priority:
    1. DATABASE_URL (recommended; Neon/local PostgreSQL)
    2. Explicit/legacy SQL Server configuration during the migration window
    3. Local PostgreSQL development default
    """

    explicit_url = normalize_database_uri(os.getenv("DATABASE_URL") or "")
    if explicit_url:
        return explicit_url

    if _should_use_legacy_sql_server():
        return _legacy_sql_server_uri()

    return normalize_database_uri(
        os.getenv(
            "LOCAL_POSTGRES_URL",
            "postgresql://lifeos:lifeos@127.0.0.1:5432/lifeos",
        )
    )


def get_direct_database_uri() -> str:
    """Return the non-pooled URL intended for migrations/admin operations."""

    direct_url = normalize_database_uri(
        os.getenv("DATABASE_DIRECT_URL") or ""
    )
    return direct_url or get_database_uri()


def is_postgres_uri(value: str) -> bool:
    return str(value or "").startswith(("postgresql://", "postgresql+"))

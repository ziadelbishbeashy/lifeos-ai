"""Database extension and connection-string helpers."""

from __future__ import annotations

import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy


load_dotenv()

db = SQLAlchemy()


def get_database_uri() -> str:
    """Build the SQLAlchemy URI without connecting to the database.

    DATABASE_URL takes priority for cloud deployment and automated tooling.
    The existing SQL Server environment variables remain fully supported.
    """

    explicit_url = (os.getenv("DATABASE_URL") or "").strip()
    if explicit_url:
        # Compatibility with providers that still emit the old PostgreSQL URI.
        if explicit_url.startswith("postgres://"):
            explicit_url = explicit_url.replace(
                "postgres://",
                "postgresql://",
                1,
            )
        return explicit_url

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

"""Alembic environment for LifeOS.

The repository preserves the historical SQL Server migration chain. Foundation
V2 targets PostgreSQL for new environments, so a *fresh* PostgreSQL database
must first receive the reviewed PostgreSQL baseline and be stamped before this
historical chain is allowed to continue. This prevents accidentally replaying
SQL Server-only revisions on Neon.

This module also supports running Alembic directly with ``python -m alembic``.
Standalone migration commands must not require booting the Flask application.
"""

from __future__ import annotations

import logging
from logging.config import fileConfig
import os

from alembic import context
from flask import current_app, has_app_context
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import NullPool

# Importing the core database module is safe because lifeos.__init__ no longer
# imports the Flask application eagerly. Import models only to register the
# complete SQLAlchemy metadata used by Alembic autogeneration/comparison.
from lifeos.core.database import (
    db,
    get_direct_database_uri,
    normalize_database_uri,
)
import models  # noqa: F401,E402


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")


def _direct_url_override() -> str:
    return normalize_database_uri(os.getenv("DATABASE_DIRECT_URL") or "")


def get_flask_engine():
    if not has_app_context():
        raise RuntimeError("Flask application context is not active.")
    extension = current_app.extensions["migrate"]
    database = extension.db
    return database.engine


def get_migration_engine():
    """Return the engine Alembic should use.

    A direct migration URL wins. When Alembic is invoked through Flask-Migrate
    we reuse Flask's configured engine. For standalone Alembic commands we
    create a short-lived engine from the same canonical database configuration
    used by the application.
    """

    direct = _direct_url_override()
    if direct:
        return create_engine(direct, poolclass=NullPool, future=True)

    if has_app_context():
        return get_flask_engine()

    return create_engine(
        get_direct_database_uri(),
        poolclass=NullPool,
        future=True,
    )


def get_engine_url() -> str:
    # Avoid creating an engine merely to render the URL in standalone mode.
    if not has_app_context():
        rendered = get_direct_database_uri()
        return rendered.replace("%", "%%")

    url = get_migration_engine().url
    try:
        rendered = url.render_as_string(hide_password=False)
    except AttributeError:
        rendered = str(url)
    return rendered.replace("%", "%%")


def get_metadata():
    if has_app_context():
        database = current_app.extensions["migrate"].db
        if hasattr(database, "metadatas"):
            return database.metadatas[None]
        return database.metadata

    if hasattr(db, "metadatas"):
        return db.metadatas[None]
    return db.metadata


config.set_main_option("sqlalchemy.url", get_engine_url())
target_metadata = get_metadata()


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _guard_fresh_postgres(connection) -> None:
    """Do not replay the historical SQL Server chain on a clean Postgres DB."""

    if connection.dialect.name != "postgresql":
        return

    if os.getenv("ALLOW_LEGACY_MIGRATION_CHAIN_ON_POSTGRES", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return

    tables = set(inspect(connection).get_table_names())
    if "alembic_version" not in tables:
        raise RuntimeError(
            "Fresh PostgreSQL/Neon databases must use the Foundation V2 "
            "PostgreSQL baseline before running the historical Alembic chain. "
            "See docs/migration/NEON_AND_POSTGRES.md."
        )


def run_migrations_online() -> None:
    direct_override = bool(_direct_url_override())
    using_flask_engine = has_app_context() and not direct_override
    connectable = get_migration_engine()

    try:
        with connectable.connect() as connection:
            _guard_fresh_postgres(connection)
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                compare_server_default=True,
                render_as_batch=connection.dialect.name == "sqlite",
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        # Flask owns/disposes its configured engine. Direct/standalone migration
        # engines are short-lived and must be disposed here.
        if not using_flask_engine:
            connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

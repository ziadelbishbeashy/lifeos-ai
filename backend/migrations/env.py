"""Alembic environment for LifeOS.

The repository preserves the historical SQL Server migration chain. Foundation
V2 targets PostgreSQL for new environments, so a *fresh* PostgreSQL database
must first receive the reviewed PostgreSQL baseline and be stamped before this
historical chain is allowed to continue. This prevents accidentally replaying
SQL Server-only revisions on Neon.
"""

from __future__ import annotations

import logging
from logging.config import fileConfig
import os

from alembic import context
from flask import current_app
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import NullPool

from database import normalize_database_uri


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")


def get_flask_engine():
    extension = current_app.extensions["migrate"]
    database = extension.db
    return database.engine


def get_migration_engine():
    """Use a direct Neon URL for migrations when one is provided."""

    direct = normalize_database_uri(os.getenv("DATABASE_DIRECT_URL") or "")
    if direct:
        return create_engine(direct, poolclass=NullPool, future=True)
    return get_flask_engine()


def get_engine_url() -> str:
    url = get_migration_engine().url
    try:
        rendered = url.render_as_string(hide_password=False)
    except AttributeError:
        rendered = str(url)
    return rendered.replace("%", "%%")


def get_metadata():
    database = current_app.extensions["migrate"].db
    if hasattr(database, "metadatas"):
        return database.metadatas[None]
    return database.metadata


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
    connectable = get_migration_engine()

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

    # Flask owns/disposes its configured engine. A direct migration engine is
    # short-lived and can be disposed here.
    if connectable is not get_flask_engine():
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""Alembic environment for LifeOS database migrations."""

from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context
from flask import current_app


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")


def get_engine():
    """Return the SQLAlchemy engine registered by Flask-Migrate."""

    extension = current_app.extensions["migrate"]
    database = extension.db
    return database.engine


def get_engine_url() -> str:
    """Return an Alembic-safe database URL without hiding credentials."""

    url = get_engine().url
    try:
        rendered = url.render_as_string(hide_password=False)
    except AttributeError:
        rendered = str(url)
    return rendered.replace("%", "%%")


def get_metadata():
    """Return the application's default SQLAlchemy metadata."""

    database = current_app.extensions["migrate"].db
    if hasattr(database, "metadatas"):
        return database.metadatas[None]
    return database.metadata


config.set_main_option("sqlalchemy.url", get_engine_url())
target_metadata = get_metadata()


def run_migrations_offline() -> None:
    """Run migrations without opening a database connection."""

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


def run_migrations_online() -> None:
    """Run migrations using the configured LifeOS database connection."""

    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

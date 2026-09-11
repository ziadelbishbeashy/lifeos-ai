"""Record the existing LifeOS schema as the migration baseline.

Revision ID: 20260726_0001
Revises: None
Create Date: 2026-07-26

This migration intentionally performs no DDL. The development SQL Server
schema existed before Flask-Migrate was introduced. Existing databases should
be stamped to this revision once, after taking a backup.
"""

from __future__ import annotations


revision = "20260726_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Keep the pre-existing schema unchanged."""

    pass


def downgrade() -> None:
    """Do not imply that the legacy schema can be removed automatically."""

    raise RuntimeError(
        "The LifeOS baseline cannot be downgraded automatically. "
        "Restore a reviewed database backup instead."
    )

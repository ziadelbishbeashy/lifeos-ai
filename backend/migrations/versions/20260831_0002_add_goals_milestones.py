"""retired I20 goals prototype compatibility revision

Revision ID: 20260831_0002
Revises: 20260831_0001
Create Date: 2026-08-31

The original Goals/Milestones prototype was intentionally retired before it
became a product dependency. This revision is retained as a no-op so databases
that already recorded 20260831_0002 remain on a valid Alembic chain. It does
not create or drop user tables: if an earlier local build created prototype
goal tables, they are left untouched until an explicit, backed-up cleanup.
"""
revision = "20260831_0002"
down_revision = "20260831_0001"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass

"""add I18 visual automation flow metadata

Revision ID: 20260830_0002
Revises: 20260830_0001
Create Date: 2026-08-30

I18 stores only validated visual layout metadata for the constrained I17
automation definition. It does not introduce executable graph nodes, arbitrary
code, arbitrary URLs, or a second automation runtime.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260830_0002"
down_revision = "20260830_0001"
branch_labels = None
depends_on = None


def _columns(bind, table: str) -> set[str]:
    return {str(item.get("name")) for item in sa.inspect(bind).get_columns(table)}


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "lifeos_automations" not in tables:
        return
    columns = _columns(bind, "lifeos_automations")
    if "visual_graph_json" not in columns:
        op.add_column(
            "lifeos_automations",
            sa.Column("visual_graph_json", sa.UnicodeText(), nullable=False, server_default="{}"),
        )


def downgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "lifeos_automations" not in tables:
        return
    if "visual_graph_json" in _columns(bind, "lifeos_automations"):
        op.drop_column("lifeos_automations", "visual_graph_json")

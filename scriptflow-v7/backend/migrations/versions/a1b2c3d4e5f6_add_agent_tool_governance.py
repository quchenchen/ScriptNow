"""add agent template tool governance

Revision ID: a1b2c3d4e5f6
Revises: f0a9b8c7d6e5
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f0a9b8c7d6e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tool_groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("tool_keys", sa.JSON(), nullable=False),
        sa.Column(
            "min_tier_id",
            sa.String(36),
            sa.ForeignKey("tiers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("key", name="uq_tool_groups_key"),
    )
    op.create_table(
        "agent_tool_mounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("role_key", sa.String(80), nullable=False),
        sa.Column(
            "tool_group_id",
            sa.String(36),
            sa.ForeignKey("tool_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("role_key", "tool_group_id", name="uq_agent_tool_mount"),
    )


def downgrade() -> None:
    op.drop_table("agent_tool_mounts")
    op.drop_table("tool_groups")

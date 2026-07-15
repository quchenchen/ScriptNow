"""props table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "props",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("significance", sa.String(20), server_default="background"),
        sa.Column("first_appearance", sa.Integer, server_default="0"),
        sa.Column("last_appearance", sa.Integer, server_default="0"),
        sa.Column("usage_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_props_project", "props", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_props_project", table_name="props")
    op.drop_table("props")

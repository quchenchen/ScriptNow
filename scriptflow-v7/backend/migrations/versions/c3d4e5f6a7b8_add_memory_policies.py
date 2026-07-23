"""add memory governance policies

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memory_policies",
        sa.Column("role_key", sa.String(80), primary_key=True),
        sa.Column("memory_max_tokens", sa.Integer(), nullable=False),
        sa.Column("trigger_ratio", sa.Numeric(4, 3), nullable=False),
        sa.Column("reserve_ratio", sa.Numeric(4, 3), nullable=False),
        sa.Column("memory_instructions", sa.String(4000), nullable=False),
        sa.Column("preserve_creative_decisions", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("memory_policies")

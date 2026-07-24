"""add explicit administrator role

Revision ID: e9f8a7b6c5d4
Revises: d8e7f6a5b4c3
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e9f8a7b6c5d4"
down_revision: str | None = "d8e7f6a5b4c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")

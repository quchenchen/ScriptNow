"""add cover output specification

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("cover_artifacts") as batch:
        batch.add_column(sa.Column("platform_key", sa.String(40), nullable=True))
        batch.add_column(sa.Column("width", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("height", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("language", sa.String(32), nullable=True))
    op.execute(
        "UPDATE cover_artifacts SET platform_key = 'custom', width = 1024, "
        "height = 1600, language = 'zh-CN'"
    )
    with op.batch_alter_table("cover_artifacts") as batch:
        batch.alter_column("platform_key", nullable=False)
        batch.alter_column("width", nullable=False)
        batch.alter_column("height", nullable=False)
        batch.alter_column("language", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("cover_artifacts") as batch:
        batch.drop_column("language")
        batch.drop_column("height")
        batch.drop_column("width")
        batch.drop_column("platform_key")

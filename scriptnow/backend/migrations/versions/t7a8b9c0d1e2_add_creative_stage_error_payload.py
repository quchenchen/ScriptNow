"""add creative stage error payload

Revision ID: t7a8b9c0d1e2
Revises: r5a6b7c8d9e0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "t7a8b9c0d1e2"
down_revision: str | None = "r5a6b7c8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("creative_stage_runs") as batch:
        batch.add_column(sa.Column("error", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("creative_stage_runs") as batch:
        batch.drop_column("error")

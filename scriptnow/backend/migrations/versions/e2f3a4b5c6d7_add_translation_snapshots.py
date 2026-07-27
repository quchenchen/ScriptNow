"""add translation snapshot content

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "translation_snapshot_contents",
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("documents", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["project_snapshots.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )


def downgrade() -> None:
    op.drop_table("translation_snapshot_contents")

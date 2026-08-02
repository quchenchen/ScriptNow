"""allow creative narrative indexes without source file

Revision ID: 0e2d2f90a50e
Revises: 74c170b8e7bd
Create Date: 2026-08-02 21:02:11.953622
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0e2d2f90a50e'
down_revision: str | None = '74c170b8e7bd'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("narrative_indexes") as batch:
        batch.alter_column(
            "source_file_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("narrative_indexes") as batch:
        batch.alter_column(
            "source_file_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )

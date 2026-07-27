"""add recoverable project deletion

Revision ID: j7e8f9a0b1c2
Revises: i6d7e8f9a0b1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "j7e8f9a0b1c2"
down_revision: str | None = "i6d7e8f9a0b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_projects_deleted_at", "projects", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_projects_deleted_at", table_name="projects")
    op.drop_column("projects", "deleted_at")

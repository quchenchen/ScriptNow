"""add novel revision provenance

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("novel_document_revisions") as batch:
        batch.add_column(sa.Column("parent_revision_id", sa.String(36), nullable=True))
        batch.add_column(
            sa.Column("source", sa.String(24), nullable=False, server_default="agent")
        )


def downgrade() -> None:
    with op.batch_alter_table("novel_document_revisions") as batch:
        batch.drop_column("source")
        batch.drop_column("parent_revision_id")

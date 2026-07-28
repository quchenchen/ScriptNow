"""add configurable language model context window

Revision ID: l9a0b1c2d3e4
Revises: k8f9a0b1c2d3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "l9a0b1c2d3e4"
down_revision: str | None = "k8f9a0b1c2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("language_models") as batch_op:
        batch_op.add_column(
            sa.Column(
                "context_window",
                sa.Integer(),
                nullable=False,
                server_default="32768",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("language_models") as batch_op:
        batch_op.drop_column("context_window")

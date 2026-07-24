"""add complete product event envelope

Revision ID: b50a1f8c90d2
Revises: 5ba366f4d8c3
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b50a1f8c90d2"
down_revision: str | None = "5ba366f4d8c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("project_events") as batch:
        batch.add_column(
            sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False)
        )
        batch.add_column(sa.Column("actor", sa.JSON(), server_default="{}", nullable=False))
        batch.add_column(sa.Column("aggregate", sa.JSON(), server_default="{}", nullable=False))
        batch.add_column(sa.Column("causation_id", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("idempotency_key", sa.String(length=160), nullable=True))
    op.execute(
        "UPDATE project_events SET idempotency_key = event_key WHERE idempotency_key IS NULL"
    )
    with op.batch_alter_table("project_events") as batch:
        batch.alter_column("idempotency_key", existing_type=sa.String(length=160), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("project_events") as batch:
        batch.drop_column("idempotency_key")
        batch.drop_column("causation_id")
        batch.drop_column("aggregate")
        batch.drop_column("actor")
        batch.drop_column("schema_version")

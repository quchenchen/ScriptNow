"""add_story_core_idempotency

Revision ID: b0f3eca19ce8
Revises: 1f0dfd3d45de
Create Date: 2026-07-18 14:08:13.215022
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b0f3eca19ce8'
down_revision: str | None = '1f0dfd3d45de'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("script_story_core_candidates") as batch:
        batch.add_column(
            sa.Column(
                "idempotency_key", sa.String(length=120), server_default="legacy", nullable=False
            )
        )
        batch.create_unique_constraint(
            "uq_script_core_request_ordinal", ["project_id", "idempotency_key", "ordinal"]
        )


def downgrade() -> None:
    with op.batch_alter_table("script_story_core_candidates") as batch:
        batch.drop_constraint("uq_script_core_request_ordinal", type_="unique")
        batch.drop_column("idempotency_key")

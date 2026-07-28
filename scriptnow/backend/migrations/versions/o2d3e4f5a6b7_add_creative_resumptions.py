"""add exactly-once creative resumption claims

Revision ID: o2d3e4f5a6b7
Revises: n1c2d3e4f5a6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "o2d3e4f5a6b7"
down_revision: str | None = "n1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "creative_resumptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("decision_request_id", sa.String(length=36), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("claimed_by", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["checkpoint_id"],
            ["creative_checkpoints.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decision_request_id"],
            ["creative_decision_requests.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["creative_operations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "decision_request_id",
            name="uq_creative_resumption_decision",
        ),
        sa.UniqueConstraint(
            "operation_id",
            "idempotency_key",
            name="uq_creative_resumption_idempotency",
        ),
    )
    op.create_index(
        "ix_creative_resumption_operation_status",
        "creative_resumptions",
        ["operation_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_creative_resumption_operation_status",
        table_name="creative_resumptions",
    )
    op.drop_table("creative_resumptions")

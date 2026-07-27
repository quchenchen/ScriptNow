"""add chapter pipeline state and revision lineage

Revision ID: k8f9a0b1c2d3
Revises: j7e8f9a0b1c2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k8f9a0b1c2d3"
down_revision: str | None = "j7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("cross_cultural_production_units") as batch_op:
        batch_op.add_column(
            sa.Column(
                "pipeline_status",
                sa.String(length=32),
                nullable=False,
                server_default="ready_for_decision",
            )
        )
        batch_op.add_column(
            sa.Column(
                "revision_kind",
                sa.String(length=16),
                nullable=False,
                server_default="agent",
            )
        )
        batch_op.add_column(sa.Column("source_unit_id", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column("context_snapshot", sa.JSON(), nullable=False, server_default="{}")
        )
        batch_op.add_column(sa.Column("review_report", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("failure_reason", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            )
        )
        batch_op.create_foreign_key(
            "fk_cross_cultural_production_unit_source",
            "cross_cultural_production_units",
            ["source_unit_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("cross_cultural_production_units") as batch_op:
        batch_op.drop_constraint("fk_cross_cultural_production_unit_source", type_="foreignkey")
        for column in (
            "updated_at",
            "failure_reason",
            "review_report",
            "context_snapshot",
            "source_unit_id",
            "revision_kind",
            "pipeline_status",
        ):
            batch_op.drop_column(column)

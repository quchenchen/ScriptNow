"""add cross-cultural production units

Revision ID: i6d7e8f9a0b1
Revises: h5c6d7e8f9a0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "i6d7e8f9a0b1"
down_revision: str | None = "h5c6d7e8f9a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cross_cultural_production_units",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recreation_id", sa.String(length=36), nullable=False),
        sa.Column("scale_plan_artifact_id", sa.String(length=36), nullable=False),
        sa.Column("work_package_key", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("feedback", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["recreation_id"], ["cross_cultural_recreations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["scale_plan_artifact_id"],
            ["cross_cultural_artifacts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recreation_id",
            "scale_plan_artifact_id",
            "work_package_key",
            "version",
            name="uq_cross_cultural_production_unit_version",
        ),
        sa.UniqueConstraint(
            "recreation_id",
            "work_package_key",
            "idempotency_key",
            name="uq_cross_cultural_production_unit_request",
        ),
    )
    op.create_index(
        "uq_cross_cultural_one_adopted_production_unit",
        "cross_cultural_production_units",
        ["recreation_id", "scale_plan_artifact_id", "work_package_key"],
        unique=True,
        sqlite_where=sa.text("status = 'adopted'"),
    )
    op.create_index(
        "ix_cross_cultural_production_unit_lookup",
        "cross_cultural_production_units",
        ["recreation_id", "scale_plan_artifact_id", "work_package_key", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cross_cultural_production_unit_lookup",
        table_name="cross_cultural_production_units",
    )
    op.drop_index(
        "uq_cross_cultural_one_adopted_production_unit",
        table_name="cross_cultural_production_units",
    )
    op.drop_table("cross_cultural_production_units")

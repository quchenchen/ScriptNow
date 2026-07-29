"""add creative delivery artifacts

Revision ID: p3e4f5a6b7c8
Revises: o2d3e4f5a6b7
"""

import sqlalchemy as sa
from alembic import op

revision = "p3e4f5a6b7c8"
down_revision = "o2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creative_delivery_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("artifact", sa.LargeBinary(), nullable=True),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "domain",
            "stage",
            "idempotency_key",
            name="uq_creative_delivery_artifact_request",
        ),
    )
    op.create_index(
        "ix_creative_delivery_artifact_lookup",
        "creative_delivery_artifacts",
        ["tenant_id", "project_id", "domain", "stage", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_creative_delivery_artifact_lookup",
        table_name="creative_delivery_artifacts",
    )
    op.drop_table("creative_delivery_artifacts")

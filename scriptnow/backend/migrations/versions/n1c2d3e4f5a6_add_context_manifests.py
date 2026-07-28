"""add immutable creative context manifests

Revision ID: n1c2d3e4f5a6
Revises: m0b1c2d3e4f5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "n1c2d3e4f5a6"
down_revision: str | None = "m0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "creative_context_manifests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("turn_id", sa.String(length=36), nullable=True),
        sa.Column("domain", sa.String(length=40), nullable=False),
        sa.Column("stage", sa.String(length=120), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("source_versions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["creative_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["turn_id"], ["creative_turns.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "content_digest",
            name="uq_creative_context_manifest_digest",
        ),
    )
    op.create_index(
        "ix_creative_context_manifest_project_created",
        "creative_context_manifests",
        ["tenant_id", "project_id", "created_at"],
    )
    with op.batch_alter_table("creative_operations") as batch:
        batch.create_foreign_key(
            "fk_creative_operation_context_manifest",
            "creative_context_manifests",
            ["context_manifest_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("creative_operations") as batch:
        batch.drop_constraint(
            "fk_creative_operation_context_manifest",
            type_="foreignkey",
        )
    op.drop_index(
        "ix_creative_context_manifest_project_created",
        table_name="creative_context_manifests",
    )
    op.drop_table("creative_context_manifests")

"""add retrieval manifests

Revision ID: q4f5a6b7c8d9
Revises: p3e4f5a6b7c8
"""

import sqlalchemy as sa
from alembic import op

revision = "q4f5a6b7c8d9"
down_revision = "p3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creative_retrieval_manifests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("domain", sa.String(length=40), nullable=False),
        sa.Column("stage", sa.String(length=120), nullable=False),
        sa.Column("operation", sa.String(length=120), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("source_versions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "project_id",
            "content_digest",
            name="uq_creative_retrieval_manifest_digest",
        ),
    )
    op.create_index(
        "ix_creative_retrieval_manifest_project_created",
        "creative_retrieval_manifests",
        ["tenant_id", "project_id", "created_at"],
    )
    with op.batch_alter_table("creative_context_manifests") as batch_op:
        batch_op.add_column(
            sa.Column("retrieval_manifest_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_creative_context_manifest_retrieval",
            "creative_retrieval_manifests",
            ["retrieval_manifest_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("creative_context_manifests") as batch_op:
        batch_op.drop_constraint(
            "fk_creative_context_manifest_retrieval",
            type_="foreignkey",
        )
        batch_op.drop_column("retrieval_manifest_id")
    op.drop_index(
        "ix_creative_retrieval_manifest_project_created",
        table_name="creative_retrieval_manifests",
    )
    op.drop_table("creative_retrieval_manifests")

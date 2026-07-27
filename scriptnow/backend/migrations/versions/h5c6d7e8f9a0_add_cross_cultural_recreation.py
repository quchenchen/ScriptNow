"""add cross-cultural story recreation

Revision ID: h5c6d7e8f9a0
Revises: g4b5c6d7e8f9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "h5c6d7e8f9a0"
down_revision: str | None = "g4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(
            sa.Column(
                "workflow_kind",
                sa.String(length=48),
                nullable=False,
                server_default="original",
            )
        )
    op.execute(
        sa.text(
            """
        UPDATE projects
        SET workflow_kind = CASE
            WHEN source_mode = 'adaptation' THEN 'adaptation'
            ELSE 'original'
        END
        """
        )
    )

    op.create_table(
        "cross_cultural_recreations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_language", sa.String(length=24), nullable=False),
        sa.Column("target_language", sa.String(length=24), nullable=False),
        sa.Column("target_market", sa.String(length=160), nullable=False),
        sa.Column("target_audience", sa.String(length=240), nullable=False),
        sa.Column("distribution_context", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_cross_cultural_recreation_project"),
    )
    op.create_index(
        "ix_cross_cultural_recreation_tenant",
        "cross_cultural_recreations",
        ["tenant_id", "project_id"],
    )
    op.create_table(
        "cross_cultural_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recreation_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=48), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("feedback", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["recreation_id"], ["cross_cultural_recreations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recreation_id",
            "kind",
            "version",
            "ordinal",
            name="uq_cross_cultural_artifact_version",
        ),
        sa.UniqueConstraint(
            "recreation_id",
            "kind",
            "idempotency_key",
            "ordinal",
            name="uq_cross_cultural_artifact_request",
        ),
    )
    op.create_index(
        "uq_cross_cultural_one_adopted",
        "cross_cultural_artifacts",
        ["recreation_id", "kind"],
        unique=True,
        sqlite_where=sa.text("status = 'adopted'"),
    )
    op.create_index(
        "ix_cross_cultural_artifact_lookup",
        "cross_cultural_artifacts",
        ["recreation_id", "kind", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cross_cultural_artifact_lookup", table_name="cross_cultural_artifacts"
    )
    op.drop_index(
        "uq_cross_cultural_one_adopted", table_name="cross_cultural_artifacts"
    )
    op.drop_table("cross_cultural_artifacts")
    op.drop_index(
        "ix_cross_cultural_recreation_tenant",
        table_name="cross_cultural_recreations",
    )
    op.drop_table("cross_cultural_recreations")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("workflow_kind")

"""add novel quality reports

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "novel_quality_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("chapter_id", sa.String(120), nullable=False),
        sa.Column("revision_id", sa.String(36), nullable=False),
        sa.Column("rubric_version", sa.String(64), nullable=False),
        sa.Column("source_profile_version", sa.String(120), nullable=True),
        sa.Column("skill_plan_fingerprint", sa.String(128), nullable=False),
        sa.Column("dimensions", sa.JSON(), nullable=False),
        sa.Column("overall_status", sa.String(24), nullable=False),
        sa.Column("maturity_score", sa.Integer(), nullable=False),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("author", sa.String(160), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["novel_document_revisions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("project_id", "idempotency_key", name="uq_novel_quality_request"),
    )
    op.create_index(
        "ix_novel_quality_revision",
        "novel_quality_reports",
        ["project_id", "chapter_id", "revision_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_novel_quality_revision", table_name="novel_quality_reports")
    op.drop_table("novel_quality_reports")

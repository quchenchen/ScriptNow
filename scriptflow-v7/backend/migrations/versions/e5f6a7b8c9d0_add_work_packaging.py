"""add work packaging and cover artifacts

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "work_packages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("synopsis", sa.String(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("language", sa.String(32), nullable=False),
        sa.Column("cover_brief", sa.JSON(), nullable=False),
        sa.Column("cover_prompt", sa.String(), nullable=False),
        sa.Column("feedback", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "version", name="uq_work_package_version"),
    )
    op.create_index("ix_work_packages_tenant_project", "work_packages", ["tenant_id", "project_id"])
    op.create_table(
        "cover_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("work_package_id", sa.String(36), nullable=False),
        sa.Column("image_model_id", sa.String(36), nullable=False),
        sa.Column("provider_request_id", sa.String(240), nullable=False),
        sa.Column("image_url", sa.String(2000), nullable=False),
        sa.Column("prompt_snapshot", sa.String(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_package_id"], ["work_packages.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["image_model_id"], ["image_models.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_cover_artifacts_tenant_project", "cover_artifacts", ["tenant_id", "project_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_cover_artifacts_tenant_project", table_name="cover_artifacts")
    op.drop_table("cover_artifacts")
    op.drop_index("ix_work_packages_tenant_project", table_name="work_packages")
    op.drop_table("work_packages")

"""add tenant agent project overrides

Revision ID: d8e7f6a5b4c3
Revises: c7d6e5f4a3b2
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8e7f6a5b4c3"
down_revision: str | None = "c7d6e5f4a3b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_agent_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_key", sa.String(80), nullable=False),
        sa.Column("custom_name", sa.String(80)),
        sa.Column("soul_override", sa.String(2000)),
        sa.Column("model_id", sa.String(36), sa.ForeignKey("language_models.id", ondelete="RESTRICT")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "project_id", "role_key", name="uq_tenant_agent_config"),
    )
    op.create_index(
        "ix_tenant_agent_config_project", "tenant_agent_configs", ["tenant_id", "project_id"]
    )


def downgrade() -> None:
    op.drop_table("tenant_agent_configs")

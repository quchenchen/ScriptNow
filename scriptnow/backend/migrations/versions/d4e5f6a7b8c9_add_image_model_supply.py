"""add image model supply

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_models",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("provider_id", sa.String(length=36), nullable=False),
        sa.Column("protocol", sa.String(length=40), nullable=False, server_default="grsai_image2"),
        sa.Column("endpoint_path", sa.String(length=240), nullable=False, server_default="/v1/api/generate"),
        sa.Column("min_tier_id", sa.String(length=36), nullable=False),
        sa.Column("price_per_image", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("default_parameters", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["min_tier_id"], ["tiers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_image_models_key"),
    )
    op.create_index(
        "ix_image_models_provider_enabled", "image_models", ["provider_id", "enabled"]
    )


def downgrade() -> None:
    op.drop_index("ix_image_models_provider_enabled", table_name="image_models")
    op.drop_table("image_models")

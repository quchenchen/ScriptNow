"""support append-only operational credit grants

Revision ID: f0a9b8c7d6e5
Revises: e9f8a7b6c5d4
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f0a9b8c7d6e5"
down_revision: str | None = "e9f8a7b6c5d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("credit_ledger") as batch:
        batch.alter_column("reservation_id", existing_type=sa.String(36), nullable=True)
        batch.alter_column("run_id", existing_type=sa.String(36), type_=sa.String(120))
        batch.add_column(sa.Column("reference_key", sa.String(120)))
        batch.create_unique_constraint("uq_credit_ledger_reference", ["reference_key"])
    op.create_table(
        "orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("tier", sa.String(32), nullable=False),
        sa.Column("token_amount", sa.Integer(), nullable=False),
        sa.Column("currency_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
        sa.Column("note", sa.String(500), nullable=False, server_default=""),
        sa.Column("actor_id", sa.String(120), nullable=False),
        sa.Column("is_mock", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_orders_tenant_created", "orders", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_table("orders")
    with op.batch_alter_table("credit_ledger") as batch:
        batch.drop_constraint("uq_credit_ledger_reference", type_="unique")
        batch.drop_column("reference_key")
        batch.alter_column("run_id", existing_type=sa.String(120), type_=sa.String(36))
        batch.alter_column("reservation_id", existing_type=sa.String(36), nullable=False)

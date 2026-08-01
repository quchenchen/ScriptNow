"""add standalone review cases

Revision ID: r5a6b7c8d9e0
Revises: q4f5a6b7c8d9
"""

import sqlalchemy as sa
from alembic import op

revision = "r5a6b7c8d9e0"
down_revision = "q4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("document_kind", sa.String(length=32), nullable=False),
        sa.Column("review_domain", sa.String(length=32), nullable=False),
        sa.Column("source_filename", sa.String(length=512), nullable=False),
        sa.Column("source_media_type", sa.String(length=160), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("source_text", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_review_cases_tenant_created",
        "review_cases",
        ["tenant_id", "created_at"],
    )
    op.create_table(
        "review_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["review_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "idempotency_key", name="uq_review_message_idempotency"),
        sa.UniqueConstraint("case_id", "sequence", name="uq_review_message_sequence"),
    )
    op.create_index(
        "ix_review_messages_case_sequence",
        "review_messages",
        ["tenant_id", "case_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index("ix_review_messages_case_sequence", table_name="review_messages")
    op.drop_table("review_messages")
    op.drop_index("ix_review_cases_tenant_created", table_name="review_cases")
    op.drop_table("review_cases")

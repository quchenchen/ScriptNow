"""add source distillation tables

Revision ID: 74c170b8e7bd
Revises: r5a6b7c8d9e0
Create Date: 2026-08-02 17:35:08.099737
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = '74c170b8e7bd'
down_revision: str | None = 'r5a6b7c8d9e0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("source_distillations"):
        op.create_table(
            "source_distillations",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("project_id", sa.String(length=36), nullable=False),
            sa.Column("idempotency_key", sa.String(length=120), nullable=False),
            sa.Column("source_file_ids", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("pass_key", sa.String(length=40), nullable=False),
            sa.Column("checkpoint", sa.JSON(), nullable=False),
            sa.Column("coverage", sa.JSON(), nullable=False),
            sa.Column("error_code", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id", "idempotency_key", name="uq_source_distillation_key"
            ),
        )
        op.create_index(
            "ix_source_distillation_project",
            "source_distillations",
            ["tenant_id", "project_id", "created_at"],
        )

    if not inspector.has_table("source_evidence"):
        op.create_table(
            "source_evidence",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("project_id", sa.String(length=36), nullable=False),
            sa.Column("distillation_id", sa.String(length=36), nullable=False),
            sa.Column("evidence_key", sa.String(length=160), nullable=False),
            sa.Column("source_file_id", sa.String(length=36), nullable=False),
            sa.Column("chunk_id", sa.String(length=36), nullable=False),
            sa.Column("source_unit", sa.String(length=240), nullable=False),
            sa.Column("ordinal", sa.Integer(), nullable=False),
            sa.Column("dimension", sa.String(length=60), nullable=False),
            sa.Column("claim", sa.Text(), nullable=False),
            sa.Column("confidence", sa.Integer(), nullable=False),
            sa.Column("inference", sa.Boolean(), nullable=False),
            sa.Column("related_evidence_ids", sa.JSON(), nullable=False),
            sa.Column("contradiction_group", sa.String(length=120), nullable=True),
            sa.Column("extraction_pass", sa.String(length=40), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["distillation_id"],
                ["source_distillations.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["source_file_id"], ["workspace_files.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(["chunk_id"], ["rag_chunks.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "distillation_id", "evidence_key", name="uq_source_evidence_key"
            ),
        )
        op.create_index(
            "ix_source_evidence_run_dimension",
            "source_evidence",
            ["distillation_id", "dimension"],
        )

    if not inspector.has_table("source_profiles"):
        op.create_table(
            "source_profiles",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("project_id", sa.String(length=36), nullable=False),
            sa.Column("distillation_id", sa.String(length=36), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("decision", sa.String(length=32), nullable=False),
            sa.Column("profile", sa.JSON(), nullable=False),
            sa.Column("evidence_ids", sa.JSON(), nullable=False),
            sa.Column("conflicts", sa.JSON(), nullable=False),
            sa.Column("exclusions", sa.JSON(), nullable=False),
            sa.Column("decision_feedback", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["distillation_id"],
                ["source_distillations.id"],
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_id", "version", name="uq_source_profile_version"),
        )
        op.create_index(
            "ix_source_profiles_project_decision",
            "source_profiles",
            ["tenant_id", "project_id", "decision"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table("source_profiles"):
        op.drop_table("source_profiles")
    if inspector.has_table("source_evidence"):
        op.drop_table("source_evidence")
    if inspector.has_table("source_distillations"):
        op.drop_table("source_distillations")

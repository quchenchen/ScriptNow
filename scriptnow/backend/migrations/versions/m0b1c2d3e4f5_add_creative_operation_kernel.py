"""add durable creative operation kernel

Revision ID: m0b1c2d3e4f5
Revises: l9a0b1c2d3e4
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "m0b1c2d3e4f5"
down_revision: str | None = "l9a0b1c2d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "creative_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("active_domain", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_creative_sessions_tenant_project",
        "creative_sessions",
        ["tenant_id", "project_id"],
    )
    op.create_table(
        "creative_turns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("actor", sa.JSON(), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["creative_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_creative_turns_session_created", "creative_turns", ["session_id", "created_at"]
    )
    op.create_table(
        "creative_operations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("turn_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("command", sa.String(length=120), nullable=False),
        sa.Column("domain", sa.String(length=40), nullable=False),
        sa.Column("stage", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("policy_snapshot", sa.JSON(), nullable=False),
        sa.Column("context_manifest_id", sa.String(length=120), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["project_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["creative_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["turn_id"], ["creative_turns.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
        sa.UniqueConstraint(
            "session_id", "idempotency_key", name="uq_creative_operation_idempotency"
        ),
    )
    op.create_index(
        "ix_creative_operations_tenant_project",
        "creative_operations",
        ["tenant_id", "project_id"],
    )
    op.create_index(
        "ix_creative_operations_status_updated",
        "creative_operations",
        ["status", "updated_at"],
    )
    op.create_table(
        "creative_stage_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("stage_key", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id"], ["creative_operations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "operation_id", "stage_key", "attempt", name="uq_creative_stage_attempt"
        ),
    )
    op.create_index(
        "ix_creative_stage_operation_status",
        "creative_stage_runs",
        ["operation_id", "status"],
    )
    op.create_table(
        "creative_checkpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("stage_run_id", sa.String(length=36), nullable=True),
        sa.Column("checkpoint_key", sa.String(length=160), nullable=False),
        sa.Column("state_format", sa.String(length=80), nullable=False),
        sa.Column("state_payload", sa.LargeBinary(), nullable=False),
        sa.Column("resume_metadata", sa.JSON(), nullable=False),
        sa.Column("is_complete", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id"], ["creative_operations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["stage_run_id"], ["creative_stage_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "operation_id", "checkpoint_key", name="uq_creative_checkpoint_key"
        ),
    )
    op.create_index(
        "ix_creative_checkpoint_operation_created",
        "creative_checkpoints",
        ["operation_id", "created_at"],
    )
    op.create_table(
        "creative_artifact_refs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("stage_run_id", sa.String(length=36), nullable=True),
        sa.Column("domain", sa.String(length=40), nullable=False),
        sa.Column("artifact_type", sa.String(length=120), nullable=False),
        sa.Column("artifact_id", sa.String(length=120), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("input_digest", sa.String(length=64), nullable=False),
        sa.Column("dependency_versions", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id"], ["creative_operations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["stage_run_id"], ["creative_stage_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "operation_id",
            "domain",
            "artifact_type",
            "artifact_id",
            "revision",
            name="uq_creative_artifact_revision",
        ),
    )
    op.create_index(
        "ix_creative_artifact_operation_status",
        "creative_artifact_refs",
        ["operation_id", "status"],
    )
    op.create_table(
        "creative_decision_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("stage_run_id", sa.String(length=36), nullable=True),
        sa.Column("artifact_ref_id", sa.String(length=36), nullable=True),
        sa.Column("checkpoint_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("prompt", sa.String(length=2000), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("impact", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.JSON(), nullable=True),
        sa.Column("decision", sa.JSON(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_ref_id"], ["creative_artifact_refs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["checkpoint_id"], ["creative_checkpoints.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"], ["creative_operations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["stage_run_id"], ["creative_stage_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "operation_id", "idempotency_key", name="uq_creative_decision_idempotency"
        ),
    )
    op.create_index(
        "ix_creative_decision_operation_status",
        "creative_decision_requests",
        ["operation_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_creative_decision_operation_status", table_name="creative_decision_requests"
    )
    op.drop_table("creative_decision_requests")
    op.drop_index("ix_creative_artifact_operation_status", table_name="creative_artifact_refs")
    op.drop_table("creative_artifact_refs")
    op.drop_index(
        "ix_creative_checkpoint_operation_created", table_name="creative_checkpoints"
    )
    op.drop_table("creative_checkpoints")
    op.drop_index("ix_creative_stage_operation_status", table_name="creative_stage_runs")
    op.drop_table("creative_stage_runs")
    op.drop_index("ix_creative_operations_status_updated", table_name="creative_operations")
    op.drop_index("ix_creative_operations_tenant_project", table_name="creative_operations")
    op.drop_table("creative_operations")
    op.drop_index("ix_creative_turns_session_created", table_name="creative_turns")
    op.drop_table("creative_turns")
    op.drop_index("ix_creative_sessions_tenant_project", table_name="creative_sessions")
    op.drop_table("creative_sessions")

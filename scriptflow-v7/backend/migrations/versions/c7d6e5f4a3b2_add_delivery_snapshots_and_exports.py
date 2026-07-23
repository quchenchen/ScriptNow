"""add delivery snapshots and domain export manifests

Revision ID: c7d6e5f4a3b2
Revises: b50a1f8c90d2
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7d6e5f4a3b2"
down_revision: str | None = "b50a1f8c90d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _export_table(name: str, unique_name: str, *, script: bool) -> None:
    columns = [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
    ]
    if script:
        columns.append(sa.Column("script_format", sa.String(32), nullable=False))
    columns.extend(
        [
            sa.Column("form", sa.String(32), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("artifact", sa.LargeBinary()),
            sa.Column("artifact_sha256", sa.String(64)),
            sa.Column("byte_size", sa.Integer()),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error", sa.String(500)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("project_id", "idempotency_key", name=unique_name),
        ]
    )
    op.create_table(name, *columns)
    op.create_index(f"ix_{name}_project_created", name, ["project_id", "created_at"])


def upgrade() -> None:
    op.create_table(
        "project_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("medium", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("trigger", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("base_snapshot_id", sa.String(36), sa.ForeignKey("project_snapshots.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "version", name="uq_project_snapshot_version"),
    )
    op.create_index("ix_project_snapshots_tenant_project", "project_snapshots", ["tenant_id", "project_id"])
    op.create_table(
        "script_snapshot_contents",
        sa.Column("snapshot_id", sa.String(36), sa.ForeignKey("project_snapshots.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("documents", sa.JSON(), nullable=False),
    )
    op.create_table(
        "novel_snapshot_contents",
        sa.Column("snapshot_id", sa.String(36), sa.ForeignKey("project_snapshots.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("documents", sa.JSON(), nullable=False),
    )
    _export_table("script_export_manifests", "uq_script_export_request", script=True)
    _export_table("novel_export_manifests", "uq_novel_export_request", script=False)


def downgrade() -> None:
    op.drop_table("novel_export_manifests")
    op.drop_table("script_export_manifests")
    op.drop_table("novel_snapshot_contents")
    op.drop_table("script_snapshot_contents")
    op.drop_table("project_snapshots")

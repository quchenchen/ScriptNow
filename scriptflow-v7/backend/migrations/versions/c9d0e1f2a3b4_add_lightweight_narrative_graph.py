"""add lightweight narrative graph

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "narrative_indexes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_file_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_file_id"], ["workspace_files.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_file_id", "version", name="uq_narrative_index_version"),
    )
    op.create_index(
        "ix_narrative_index_project",
        "narrative_indexes",
        ["tenant_id", "project_id", "created_at"],
    )
    op.create_table(
        "narrative_text_units",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("index_id", sa.String(length=36), nullable=False),
        sa.Column("source_file_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("chapter_key", sa.String(length=120), nullable=False),
        sa.Column("chapter_title", sa.String(length=300), nullable=False),
        sa.Column("unit_type", sa.String(length=40), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("contextual_header", sa.String(length=500), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["index_id"], ["narrative_indexes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_file_id"], ["workspace_files.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("index_id", "ordinal", name="uq_narrative_unit_ordinal"),
    )
    op.create_index(
        "ix_narrative_unit_chapter",
        "narrative_text_units",
        ["index_id", "chapter_key", "ordinal"],
    )
    op.create_table(
        "narrative_nodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("index_id", sa.String(length=36), nullable=False),
        sa.Column("node_key", sa.String(length=160), nullable=False),
        sa.Column("node_type", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("evidence_unit_ids", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["index_id"], ["narrative_indexes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("index_id", "node_key", name="uq_narrative_node_key"),
    )
    op.create_index("ix_narrative_node_type", "narrative_nodes", ["index_id", "node_type"])
    op.create_table(
        "narrative_edges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("index_id", sa.String(length=36), nullable=False),
        sa.Column("edge_key", sa.String(length=180), nullable=False),
        sa.Column("edge_type", sa.String(length=80), nullable=False),
        sa.Column("source_node_id", sa.String(length=36), nullable=False),
        sa.Column("target_node_id", sa.String(length=36), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("evidence_unit_ids", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("inference", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["index_id"], ["narrative_indexes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_node_id"], ["narrative_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_node_id"], ["narrative_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("index_id", "edge_key", name="uq_narrative_edge_key"),
    )
    op.create_index(
        "ix_narrative_edge_nodes",
        "narrative_edges",
        ["index_id", "source_node_id", "target_node_id"],
    )
    op.create_table(
        "narrative_summaries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("index_id", sa.String(length=36), nullable=False),
        sa.Column("summary_key", sa.String(length=180), nullable=False),
        sa.Column("level", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("child_unit_ids", sa.JSON(), nullable=False),
        sa.Column("child_summary_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_node_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["index_id"], ["narrative_indexes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("index_id", "summary_key", name="uq_narrative_summary_key"),
    )
    op.create_index("ix_narrative_summary_level", "narrative_summaries", ["index_id", "level"])


def downgrade() -> None:
    op.drop_index("ix_narrative_summary_level", table_name="narrative_summaries")
    op.drop_table("narrative_summaries")
    op.drop_index("ix_narrative_edge_nodes", table_name="narrative_edges")
    op.drop_table("narrative_edges")
    op.drop_index("ix_narrative_node_type", table_name="narrative_nodes")
    op.drop_table("narrative_nodes")
    op.drop_index("ix_narrative_unit_chapter", table_name="narrative_text_units")
    op.drop_table("narrative_text_units")
    op.drop_index("ix_narrative_index_project", table_name="narrative_indexes")
    op.drop_table("narrative_indexes")

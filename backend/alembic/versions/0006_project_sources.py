"""project_sources + source_chunks tables + projects.source_mode/seed_content.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-15

Adds:
- ``project_sources`` — one uploaded document per project
- ``source_chunks`` — chunked text + optional embedding
- ``projects.source_mode`` — original_pitch / original_synopsis /
  original_theme / adapted / rewrite
- ``projects.seed_content`` — the pitch / synopsis / theme text for
  original modes
- ``projects.original_work`` — original title for adaptation mode
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # project_sources
    op.create_table(
        "project_sources",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime", sa.String(80), server_default=""),
        sa.Column("file_path", sa.String(500), server_default=""),
        sa.Column("size_bytes", sa.Integer, server_default="0"),
        sa.Column("total_chars", sa.Integer, server_default="0"),
        sa.Column("chunk_count", sa.Integer, server_default="0"),
        sa.Column("summary", sa.Text, server_default=""),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("error", sa.Text, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_project_sources_project", "project_sources", ["project_id"])

    # source_chunks
    op.create_table(
        "source_chunks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("project_sources.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("char_start", sa.Integer, server_default="0"),
        sa.Column("char_end", sa.Integer, server_default="0"),
        sa.Column("embedding", sa.LargeBinary, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_source_chunks_source", "source_chunks", ["source_id"])

    # projects.* new fields
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("source_mode", sa.String(30), server_default="original_pitch"))
        batch.add_column(sa.Column("seed_content", sa.Text, server_default=""))
        batch.add_column(sa.Column("original_work", sa.String(200), server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("original_work")
        batch.drop_column("seed_content")
        batch.drop_column("source_mode")

    op.drop_index("ix_source_chunks_source", table_name="source_chunks")
    op.drop_table("source_chunks")
    op.drop_index("ix_project_sources_project", table_name="project_sources")
    op.drop_table("project_sources")

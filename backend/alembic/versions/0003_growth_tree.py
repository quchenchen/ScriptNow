"""growth_nodes + growth_edges tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-15

Introduces the growth tree tables (see ADR-0001 and issue #10). No data
migration — historical projects get backfilled by the
``scripts.backfill_growth_tree`` CLI, run out-of-band.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "growth_nodes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("node_type", sa.String(20), nullable=False),
        sa.Column("ref_id", sa.Integer, nullable=True),
        sa.Column("label", sa.String(200), server_default=""),
        sa.Column("metadata", sa.Text, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_growth_nodes_project", "growth_nodes", ["project_id"])
    op.create_index(
        "ix_growth_nodes_ref", "growth_nodes", ["node_type", "ref_id"],
    )

    op.create_table(
        "growth_edges",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("from_node_id", sa.Integer, sa.ForeignKey("growth_nodes.id"), nullable=False),
        sa.Column("to_node_id", sa.Integer, sa.ForeignKey("growth_nodes.id"), nullable=False),
        sa.Column("edge_type", sa.String(20), nullable=False, server_default="derived_from"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_growth_edges_project", "growth_edges", ["project_id"])
    op.create_index("ix_growth_edges_from", "growth_edges", ["from_node_id"])
    op.create_index("ix_growth_edges_to", "growth_edges", ["to_node_id"])


def downgrade() -> None:
    op.drop_index("ix_growth_edges_to", table_name="growth_edges")
    op.drop_index("ix_growth_edges_from", table_name="growth_edges")
    op.drop_index("ix_growth_edges_project", table_name="growth_edges")
    op.drop_table("growth_edges")
    op.drop_index("ix_growth_nodes_ref", table_name="growth_nodes")
    op.drop_index("ix_growth_nodes_project", table_name="growth_nodes")
    op.drop_table("growth_nodes")

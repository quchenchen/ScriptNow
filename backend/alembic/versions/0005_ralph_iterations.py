"""ralph_iterations table + project-level Ralph thresholds.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ralph_iterations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("episode_id", sa.Integer, sa.ForeignKey("episodes.id"), nullable=False),
        sa.Column("iteration", sa.Integer, nullable=False),
        sa.Column("writing_output", sa.Text, server_default=""),
        sa.Column("review_score", sa.Float, server_default="0"),
        sa.Column("review_dimensions", sa.Text, server_default="{}"),
        sa.Column("review_issues", sa.Text, server_default="[]"),
        sa.Column("decision", sa.String(20), server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ralph_iterations_episode", "ralph_iterations", ["episode_id"])

    # Project-level Ralph thresholds
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("ralph_pass_threshold", sa.Float, server_default="85"))
        batch.add_column(sa.Column("ralph_revise_threshold", sa.Float, server_default="60"))
        batch.add_column(sa.Column("ralph_max_retries", sa.Integer, server_default="3"))


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("ralph_max_retries")
        batch.drop_column("ralph_revise_threshold")
        batch.drop_column("ralph_pass_threshold")

    op.drop_index("ix_ralph_iterations_episode", table_name="ralph_iterations")
    op.drop_table("ralph_iterations")

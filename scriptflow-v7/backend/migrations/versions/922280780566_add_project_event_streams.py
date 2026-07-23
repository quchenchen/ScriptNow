"""add_project_event_streams

Revision ID: 922280780566
Revises: b0f3eca19ce8
Create Date: 2026-07-18 14:21:25.848896
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '922280780566'
down_revision: str | None = 'b0f3eca19ce8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_events", sa.Column("stream_key", sa.String(length=100), nullable=True)
    )
    op.execute("UPDATE project_events SET stream_key = 'run:' || run_id")
    with op.batch_alter_table("project_events") as batch:
        batch.alter_column("stream_key", existing_type=sa.String(length=100), nullable=False)
        batch.alter_column("run_id", existing_type=sa.String(length=36), nullable=True)
        batch.create_unique_constraint(
            "uq_project_events_stream_key", ["stream_key", "event_key"]
        )
        batch.create_unique_constraint(
            "uq_project_events_stream_sequence", ["stream_key", "sequence"]
        )


def downgrade() -> None:
    op.execute("DELETE FROM project_events WHERE run_id IS NULL")
    with op.batch_alter_table("project_events") as batch:
        batch.drop_constraint("uq_project_events_stream_sequence", type_="unique")
        batch.drop_constraint("uq_project_events_stream_key", type_="unique")
        batch.alter_column("run_id", existing_type=sa.String(length=36), nullable=False)
        batch.drop_column("stream_key")

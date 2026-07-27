"""add translation correction queue

Revision ID: g4b5c6d7e8f9
Revises: f3a4b5c6d7e8
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "g4b5c6d7e8f9"
down_revision: str | None = "f3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "translation_corrections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("term_id", sa.String(length=36), nullable=False),
        sa.Column("chapter_id", sa.String(length=120), nullable=False),
        sa.Column("previous_target", sa.String(length=240), nullable=False),
        sa.Column("required_target", sa.String(length=240), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["term_id"], ["translation_glossary_terms.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_translation_correction_project_status",
        "translation_corrections",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_translation_correction_term_status",
        "translation_corrections",
        ["term_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_translation_correction_term_status",
        table_name="translation_corrections",
    )
    op.drop_index(
        "ix_translation_correction_project_status",
        table_name="translation_corrections",
    )
    op.drop_table("translation_corrections")

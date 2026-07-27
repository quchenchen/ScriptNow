"""add persistent translation glossary

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: str | None = "e2f3a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "translation_glossary_terms",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_term", sa.String(length=240), nullable=False),
        sa.Column("target_term", sa.String(length=240), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "source_term", name="uq_translation_glossary_source"
        ),
    )
    op.create_index(
        "ix_translation_glossary_project_status",
        "translation_glossary_terms",
        ["project_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_translation_glossary_project_status",
        table_name="translation_glossary_terms",
    )
    op.drop_table("translation_glossary_terms")

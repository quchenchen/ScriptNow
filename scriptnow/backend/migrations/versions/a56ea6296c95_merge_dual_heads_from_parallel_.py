"""merge dual heads from parallel development

Revision ID: a56ea6296c95
Revises: 0e2d2f90a50e, t7a8b9c0d1e2
Create Date: 2026-08-05 17:41:10.917516
"""
from collections.abc import Sequence

revision: str = 'a56ea6296c95'
down_revision: str | None = ('0e2d2f90a50e', 't7a8b9c0d1e2')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

"""Add requested_at column to evidence table.

Revision ID: 0002_add_evidence_requested_at
Revises: 0001_initial_schema
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_add_evidence_requested_at"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evidence",
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evidence", "requested_at")

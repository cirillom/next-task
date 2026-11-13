"""Preserve tasks while allowing reversible abandonment.

Revision ID: b83d0f524916
Revises: a72c9e413805
"""

import sqlalchemy as sa
from alembic import op

revision = "b83d0f524916"
down_revision = "a72c9e413805"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("abandoned_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "abandoned_at")

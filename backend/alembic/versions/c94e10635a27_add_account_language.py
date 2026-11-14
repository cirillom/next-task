"""Persist account and invitation language without changing user content.

Revision ID: c94e10635a27
Revises: b83d0f524916
"""

import sqlalchemy as sa
from alembic import op

revision = "c94e10635a27"
down_revision = "b83d0f524916"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("users", "invitations"):
        op.add_column(
            table, sa.Column("language", sa.String(16), nullable=False, server_default="en")
        )


def downgrade() -> None:
    for table in ("invitations", "users"):
        op.drop_column(table, "language")

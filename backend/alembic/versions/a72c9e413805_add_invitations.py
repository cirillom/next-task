"""Add one expiring invitation per email address.

Revision ID: a72c9e413805
Revises: f61e8ac94207
"""

import sqlalchemy as sa
from alembic import op

revision = "a72c9e413805"
down_revision = "f61e8ac94207"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invitations",
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("email"),
        sa.UniqueConstraint("token_hash"),
    )


def downgrade() -> None:
    op.drop_table("invitations")

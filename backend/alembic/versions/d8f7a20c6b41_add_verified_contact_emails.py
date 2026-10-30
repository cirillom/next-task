"""Add separate verified contact emails and pending verification tokens.

Revision ID: d8f7a20c6b41
Revises: c518b2d7e4f0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8f7a20c6b41"
down_revision: str | None = "c518b2d7e4f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("contact_email", sa.String(length=320), nullable=True))
    op.add_column("users", sa.Column("contact_email_verified_at", sa.DateTime(timezone=True)))
    op.create_index("ix_users_contact_email", "users", ["contact_email"], unique=True)
    op.create_table(
        "email_verifications",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("token_hash"),
    )


def downgrade() -> None:
    op.drop_table("email_verifications")
    op.drop_index("ix_users_contact_email", table_name="users")
    op.drop_column("users", "contact_email_verified_at")
    op.drop_column("users", "contact_email")

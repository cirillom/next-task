"""Store login attempts for sliding IP windows.

Revision ID: c518b2d7e4f0
Revises: a97d4e32c810
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c518b2d7e4f0"
down_revision: str | None = "a97d4e32c810"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_login_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_auth_login_attempts_key_created_at",
        "auth_login_attempts",
        ["key", "created_at"],
    )
    op.create_index("ix_auth_login_attempts_created_at", "auth_login_attempts", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_login_attempts_created_at", table_name="auth_login_attempts")
    op.drop_index("ix_auth_login_attempts_key_created_at", table_name="auth_login_attempts")
    op.drop_table("auth_login_attempts")

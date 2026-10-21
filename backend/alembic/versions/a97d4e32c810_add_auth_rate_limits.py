"""Persist authentication attempt limits.

Revision ID: a97d4e32c810
Revises: b64c9a2e7f10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a97d4e32c810"
down_revision: str | None = "b64c9a2e7f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_rate_limits",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_auth_rate_limits_window_started_at", "auth_rate_limits", ["window_started_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_auth_rate_limits_window_started_at", table_name="auth_rate_limits")
    op.drop_table("auth_rate_limits")

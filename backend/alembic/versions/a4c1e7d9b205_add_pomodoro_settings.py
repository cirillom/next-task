"""add pomodoro settings

Revision ID: a4c1e7d9b205
Revises: 8d2f4b7c1a90
Create Date: 2026-09-04 15:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4c1e7d9b205"
down_revision: str | None = "8d2f4b7c1a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pomodoro_settings",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("focus_minutes", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("short_break_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("long_break_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("short_breaks_before_long", sa.Integer(), nullable=False, server_default="3"),
        sa.CheckConstraint(
            "focus_minutes BETWEEN 1 AND 180", name="pomodoro_focus_minutes_range"
        ),
        sa.CheckConstraint(
            "short_break_minutes BETWEEN 1 AND 60",
            name="pomodoro_short_break_minutes_range",
        ),
        sa.CheckConstraint(
            "long_break_minutes BETWEEN 1 AND 180",
            name="pomodoro_long_break_minutes_range",
        ),
        sa.CheckConstraint(
            "short_breaks_before_long BETWEEN 1 AND 12",
            name="pomodoro_short_breaks_before_long_range",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("pomodoro_settings")

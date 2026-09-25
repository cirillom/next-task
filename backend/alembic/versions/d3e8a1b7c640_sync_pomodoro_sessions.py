"""sync pomodoro sessions

Revision ID: d3e8a1b7c640
Revises: c92f7a1d4e30
Create Date: 2026-09-25 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3e8a1b7c640"
down_revision: str | None = "c92f7a1d4e30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("pomodoro_settings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "alert_mode",
                sa.String(length=20),
                server_default="notification",
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "pomodoro_alert_mode", "alert_mode IN ('notification', 'alarm')"
        )

    op.create_table(
        "pomodoro_sessions",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("phase", sa.String(length=20), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("short_breaks_taken", sa.Integer(), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "phase IN ('focus', 'short-break', 'long-break')", name="pomodoro_session_phase"
        ),
        sa.CheckConstraint(
            "state IN ('ready', 'running', 'ringing')", name="pomodoro_session_state"
        ),
        sa.CheckConstraint(
            "short_breaks_taken >= 0", name="pomodoro_short_breaks_taken_positive"
        ),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("pomodoro_sessions")
    with op.batch_alter_table("pomodoro_settings") as batch_op:
        batch_op.drop_constraint("pomodoro_alert_mode", type_="check")
        batch_op.drop_column("alert_mode")

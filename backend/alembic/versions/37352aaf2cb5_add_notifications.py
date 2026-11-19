"""add notifications

Revision ID: 37352aaf2cb5
Revises: c94e10635a27
Create Date: 2026-11-19 16:04:59.913202
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "37352aaf2cb5"
down_revision: str | None = "c94e10635a27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(length=2048), nullable=False),
        sa.Column("p256dh", sa.String(length=256), nullable=False),
        sa.Column("auth", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint"),
    )
    with op.batch_alter_table("push_subscriptions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_push_subscriptions_user_id"), ["user_id"], unique=False
        )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("dedup_key", sa.String(length=200), nullable=False),
        sa.Column("task_title", sa.String(length=500), nullable=False),
        sa.Column("extra_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('due', 'unblocked', 'unblocked_due', 'unblocked_overdue')",
            name="notification_kind",
        ),
        sa.CheckConstraint("extra_count >= 0", name="notification_extra_count_non_negative"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "dedup_key", name="uq_notifications_user_dedup"),
    )
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.create_index(
            "ix_notifications_user_created", ["user_id", "created_at"], unique=False
        )

    with op.batch_alter_table("task_blocks", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("auto_unblock", sa.Boolean(), server_default=sa.text("0"), nullable=False)
        )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("notification_timezone", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("notification_timezone")

    with op.batch_alter_table("task_blocks", schema=None) as batch_op:
        batch_op.drop_column("auto_unblock")

    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.drop_index("ix_notifications_user_created")

    op.drop_table("notifications")
    with op.batch_alter_table("push_subscriptions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_push_subscriptions_user_id"))

    op.drop_table("push_subscriptions")

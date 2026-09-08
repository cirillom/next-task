"""allow priority zero task drafts

Revision ID: c92f7a1d4e30
Revises: b71f3c9d4e20
Create Date: 2026-09-08 14:45:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c92f7a1d4e30"
down_revision: str | None = "b71f3c9d4e20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_constraint("task_priority_positive", type_="check")
        batch_op.create_check_constraint("task_priority_positive", "priority >= 0")


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_constraint("task_priority_positive", type_="check")
        batch_op.create_check_constraint("task_priority_positive", "priority >= 1")

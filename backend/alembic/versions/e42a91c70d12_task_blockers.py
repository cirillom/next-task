"""allow task-based and multiple active blockers

Revision ID: e42a91c70d12
Revises: d3e8a1b7c640
"""

import runpy
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "e42a91c70d12"
down_revision: str | None = "d3e8a1b7c640"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS task_blocks_one_active_update")
    op.execute("DROP TRIGGER IF EXISTS task_blocks_one_active_insert")
    op.drop_index("task_one_active_block", table_name="task_blocks")
    with op.batch_alter_table("task_blocks") as batch:
        batch.alter_column("reason", existing_type=sa.Text(), nullable=True)
        batch.add_column(sa.Column("blocking_task_id", sa.Integer()))
        batch.create_foreign_key(
            "fk_task_blocks_blocking_task_id",
            "tasks",
            ["blocking_task_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            "task_block_kind",
            "(reason IS NOT NULL AND blocking_task_id IS NULL) OR "
            "(reason IS NULL AND blocking_task_id IS NOT NULL)",
        )
    op.create_index("ix_task_blocks_blocking_task_id", "task_blocks", ["blocking_task_id"])
    op.create_index(
        "task_one_active_task_block",
        "task_blocks",
        ["task_id", "blocking_task_id"],
        unique=True,
        sqlite_where=sa.text("blocking_task_id IS NOT NULL AND unblocked_at IS NULL"),
    )


def downgrade() -> None:
    op.execute("""
        UPDATE task_blocks
        SET reason = 'Blocked by task #' || blocking_task_id, blocking_task_id = NULL
        WHERE blocking_task_id IS NOT NULL
    """)
    op.execute("""
        UPDATE task_blocks SET unblocked_at = CURRENT_TIMESTAMP
        WHERE unblocked_at IS NULL AND id NOT IN (
            SELECT MAX(id) FROM task_blocks WHERE unblocked_at IS NULL GROUP BY task_id
        )
    """)
    op.drop_index("task_one_active_task_block", table_name="task_blocks")
    op.drop_index("ix_task_blocks_blocking_task_id", table_name="task_blocks")
    with op.batch_alter_table("task_blocks") as batch:
        batch.drop_constraint("task_block_kind", type_="check")
        batch.drop_column("blocking_task_id")
        batch.alter_column("reason", existing_type=sa.Text(), nullable=False)
    op.create_index(
        "task_one_active_block",
        "task_blocks",
        ["task_id"],
        unique=True,
        sqlite_where=sa.text("unblocked_at IS NULL"),
    )
    previous = runpy.run_path(
        str(Path(__file__).with_name("b71f3c9d4e20_enforce_scheduled_active_blocks.py"))
    )
    op.execute(previous["INSERT_TRIGGER"])
    op.execute(previous["UPDATE_TRIGGER"])

"""enforce scheduled active block integrity

Revision ID: b71f3c9d4e20
Revises: a4c1e7d9b205
Create Date: 2026-09-05 20:30:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b71f3c9d4e20"
down_revision: str | None = "a4c1e7d9b205"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INSERT_TRIGGER = """
CREATE TRIGGER task_blocks_one_active_insert
BEFORE INSERT ON task_blocks
WHEN
    (NEW.unblocked_at IS NULL OR NEW.unblocked_at > CURRENT_TIMESTAMP)
    AND EXISTS (
        SELECT 1
        FROM task_blocks AS existing
        WHERE existing.task_id = NEW.task_id
          AND (existing.unblocked_at IS NULL OR existing.unblocked_at > CURRENT_TIMESTAMP)
    )
BEGIN
    SELECT RAISE(ABORT, 'Task is already blocked');
END
"""

UPDATE_TRIGGER = """
CREATE TRIGGER task_blocks_one_active_update
BEFORE UPDATE OF task_id, unblocked_at ON task_blocks
WHEN
    (NEW.unblocked_at IS NULL OR NEW.unblocked_at > CURRENT_TIMESTAMP)
    AND EXISTS (
        SELECT 1
        FROM task_blocks AS existing
        WHERE existing.task_id = NEW.task_id
          AND existing.id != OLD.id
          AND (existing.unblocked_at IS NULL OR existing.unblocked_at > CURRENT_TIMESTAMP)
    )
BEGIN
    SELECT RAISE(ABORT, 'Task is already blocked');
END
"""


def upgrade() -> None:
    op.execute(INSERT_TRIGGER)
    op.execute(UPDATE_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS task_blocks_one_active_update")
    op.execute("DROP TRIGGER IF EXISTS task_blocks_one_active_insert")

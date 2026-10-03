"""Move status score values and task assignments into tags.

Revision ID: c4a1f593d078
Revises: f6c7a0d92e31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4a1f593d078"
down_revision: str | None = "f6c7a0d92e31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 0:
            raise RuntimeError("SQLite foreign keys must be disabled for the task table rebuild")
    op.add_column("tags", sa.Column("score_value", sa.Float(), server_default="0", nullable=False))
    tags = sa.table(
        "tags",
        sa.column("id", sa.Integer()),
        sa.column("workspace_id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("score_value", sa.Float()),
    )
    task_tags = sa.table(
        "task_tags", sa.column("task_id", sa.Integer()), sa.column("tag_id", sa.Integer())
    )
    used_names: dict[int, set[str]] = {}
    for row in connection.execute(sa.select(tags.c.workspace_id, tags.c.name)):
        used_names.setdefault(row.workspace_id, set()).add(row.name.casefold())

    statuses = connection.execute(
        sa.text("SELECT id, workspace_id, name, score_value FROM task_statuses ORDER BY id")
    ).mappings()
    for old_status in statuses:
        workspace_id = old_status["workspace_id"]
        names = used_names.setdefault(workspace_id, set())
        name = old_status["name"]
        if name.casefold() in names:
            name = f"{name} (status)"
            suffix = 2
            while name.casefold() in names:
                name = f"{old_status['name']} (status {suffix})"
                suffix += 1
        names.add(name.casefold())
        tag_id = connection.execute(
            sa.insert(tags)
            .values(
                workspace_id=workspace_id,
                name=name,
                score_value=old_status["score_value"],
            )
            .returning(tags.c.id)
        ).scalar_one()
        task_ids = list(
            connection.execute(
                sa.text("SELECT id FROM tasks WHERE status_id = :status_id"),
                {"status_id": old_status["id"]},
            ).scalars()
        )
        if task_ids:
            connection.execute(
                sa.insert(task_tags),
                [{"task_id": task_id, "tag_id": tag_id} for task_id in task_ids],
            )

    connection.execute(
        sa.text(
            "UPDATE workspaces SET scoring_formula = "
            "replace(scoring_formula, 'statusValue', 'tagValue') "
            "WHERE scoring_formula LIKE '%statusValue%'"
        )
    )
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_index("ix_tasks_status_id")
        batch_op.drop_column("status_id")
    op.drop_table("task_statuses")
    if connection.dialect.name == "sqlite":
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Migration left broken foreign keys: {violations}")


def downgrade() -> None:
    raise RuntimeError("Status removal cannot be reversed without losing tag assignments")

"""move workspace data into user-owned tasks, statuses, and tags

Revision ID: f3a91c7d2e40
Revises: e42a91c70d12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3a91c7d2e40"
down_revision: str | None = "e42a91c70d12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rows(connection: sa.Connection, table: str) -> list[dict]:
    return [dict(row) for row in connection.execute(sa.text(f"SELECT * FROM {table}")).mappings()]


def _unique_name(name: str, used: set[str], limit: int) -> str:
    if name.casefold() not in used:
        used.add(name.casefold())
        return name
    number = 2
    while True:
        suffix = f" ({number})"
        candidate = f"{name[: limit - len(suffix)]}{suffix}"
        if candidate.casefold() not in used:
            used.add(candidate.casefold())
            return candidate
        number += 1


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    if connection.exec_driver_sql("PRAGMA foreign_keys").scalar() != 0:
        raise RuntimeError("Disable SQLite foreign keys before rebuilding workspace tables")

    users = _rows(connection, "users")
    workspaces = {row["id"]: row for row in _rows(connection, "workspaces")}
    members = _rows(connection, "workspace_members")
    statuses = _rows(connection, "task_statuses")
    tags = _rows(connection, "tags")
    tasks = _rows(connection, "tasks")
    task_tags = _rows(connection, "task_tags")
    tag_relationships = _rows(connection, "tag_relationships")
    blocks = _rows(connection, "task_blocks")
    sessions = _rows(connection, "pomodoro_sessions")
    tasks_by_id = {row["id"]: row for row in tasks}
    tags_by_id = {row["id"]: row for row in tags}
    statuses_by_id = {row["id"]: row for row in statuses}

    sources: dict[int, set[int]] = {row["id"]: set() for row in users}
    for row in members:
        sources[row["user_id"]].add(row["workspace_id"])
    for row in tasks:
        sources[row["created_by_user_id"]].add(row["workspace_id"])
        sources[row["created_by_user_id"]].add(statuses_by_id[row["status_id"]]["workspace_id"])
    for row in task_tags:
        user_id = tasks_by_id[row["task_id"]]["created_by_user_id"]
        sources[user_id].add(tags_by_id[row["tag_id"]]["workspace_id"])
    for row in sessions:
        sources[row["user_id"]].add(row["workspace_id"])
        if row["tag_id"] is not None:
            sources[row["user_id"]].add(tags_by_id[row["tag_id"]]["workspace_id"])

    op.add_column("users", sa.Column("scoring_formula", sa.Text(), nullable=True))
    for user in users:
        user_id = user["id"]
        owned = [
            member["workspace_id"]
            for member in members
            if member["user_id"] == user_id and member["role"] == "owner"
        ]
        choices = owned or list(sources[user_id])
        if choices:
            selected = min(choices, key=lambda item: (workspaces[item]["created_at"], item))
            connection.execute(
                sa.text("UPDATE users SET scoring_formula=:formula WHERE id=:user_id"),
                {"formula": workspaces[selected]["scoring_formula"], "user_id": user_id},
            )

    op.execute("""
        CREATE TABLE new_task_statuses (
            id INTEGER NOT NULL PRIMARY KEY, user_id INTEGER NOT NULL,
            name VARCHAR(80) NOT NULL,
            score_value FLOAT NOT NULL DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, name)
        )
    """)
    op.execute("""
        CREATE TABLE new_tags (
            id INTEGER NOT NULL PRIMARY KEY, user_id INTEGER NOT NULL,
            name VARCHAR(120) NOT NULL,
            description TEXT, color VARCHAR(32),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, name)
        )
    """)
    op.execute("""
        CREATE TABLE new_tasks (
            id INTEGER NOT NULL PRIMARY KEY, user_id INTEGER NOT NULL,
            title VARCHAR(500) NOT NULL,
            description TEXT, status_id INTEGER NOT NULL, priority INTEGER NOT NULL DEFAULT 1,
            due_date DATE, last_worked_at DATETIME, finished_at DATETIME, parent_task_id INTEGER,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT task_priority_positive CHECK (priority >= 0),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY(status_id) REFERENCES new_task_statuses(id) ON DELETE RESTRICT,
            FOREIGN KEY(parent_task_id) REFERENCES new_tasks(id) ON DELETE SET NULL
        )
    """)
    op.execute("""
        CREATE TABLE new_task_tags (
            task_id INTEGER NOT NULL, tag_id INTEGER NOT NULL,
            PRIMARY KEY(task_id, tag_id),
            FOREIGN KEY(task_id) REFERENCES new_tasks(id) ON DELETE CASCADE,
            FOREIGN KEY(tag_id) REFERENCES new_tags(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE new_tag_relationships (
            child_tag_id INTEGER NOT NULL, parent_tag_id INTEGER NOT NULL,
            PRIMARY KEY(child_tag_id, parent_tag_id),
            FOREIGN KEY(child_tag_id) REFERENCES new_tags(id) ON DELETE CASCADE,
            FOREIGN KEY(parent_tag_id) REFERENCES new_tags(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE new_task_blocks (
            id INTEGER NOT NULL PRIMARY KEY, task_id INTEGER NOT NULL, reason TEXT,
            blocked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, unblocked_at DATETIME,
            blocking_task_id INTEGER,
            CONSTRAINT task_block_kind CHECK (
                (reason IS NOT NULL AND blocking_task_id IS NULL) OR
                (reason IS NULL AND blocking_task_id IS NOT NULL)
            ),
            FOREIGN KEY(task_id) REFERENCES new_tasks(id) ON DELETE CASCADE,
            FOREIGN KEY(blocking_task_id) REFERENCES new_tasks(id) ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE TABLE new_pomodoro_sessions (
            user_id INTEGER NOT NULL PRIMARY KEY, tag_id INTEGER, task_id INTEGER,
            phase VARCHAR(20) NOT NULL, state VARCHAR(20) NOT NULL,
            short_breaks_taken INTEGER NOT NULL, ends_at DATETIME,
            CONSTRAINT pomodoro_session_phase
                CHECK (phase IN ('focus', 'short-break', 'long-break')),
            CONSTRAINT pomodoro_session_state CHECK (state IN ('ready', 'running', 'ringing')),
            CONSTRAINT pomodoro_short_breaks_taken_positive CHECK (short_breaks_taken >= 0),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(tag_id) REFERENCES new_tags(id) ON DELETE SET NULL,
            FOREIGN KEY(task_id) REFERENCES new_tasks(id) ON DELETE SET NULL
        )
    """)

    status_map: dict[tuple[int, int], int] = {}
    tag_map: dict[tuple[int, int], int] = {}
    next_status_id = 1
    next_tag_id = 1
    related_tag_ids = {
        tag_id
        for row in tag_relationships
        for tag_id in (row["child_tag_id"], row["parent_tag_id"])
    }

    for user in users:
        user_id = user["id"]
        workspace_ids = sources[user_id]
        used_status_names: set[str] = set()
        equivalent_statuses: dict[tuple[str, float], int] = {}
        for old in sorted(statuses, key=lambda item: (item["workspace_id"], item["id"])):
            if old["workspace_id"] not in workspace_ids:
                continue
            identity = (old["name"].casefold(), old["score_value"])
            if identity in equivalent_statuses:
                status_map[(user_id, old["id"])] = equivalent_statuses[identity]
                continue
            name = _unique_name(old["name"], used_status_names, 80)
            connection.execute(
                sa.text("""
                    INSERT INTO new_task_statuses (id, user_id, name, score_value)
                    VALUES (:id, :user_id, :name, :score_value)
                """),
                {
                    "id": next_status_id,
                    "user_id": user_id,
                    "name": name,
                    "score_value": old["score_value"],
                },
            )
            equivalent_statuses[identity] = next_status_id
            status_map[(user_id, old["id"])] = next_status_id
            next_status_id += 1
        if not used_status_names:
            for name, score_value in (("todo", 0), ("doing", 1)):
                connection.execute(
                    sa.text("""
                        INSERT INTO new_task_statuses (id, user_id, name, score_value)
                        VALUES (:id, :user_id, :name, :score_value)
                    """),
                    {
                        "id": next_status_id,
                        "user_id": user_id,
                        "name": name,
                        "score_value": score_value,
                    },
                )
                next_status_id += 1

        used_tag_names: set[str] = set()
        equivalent_tags: dict[tuple[str, str | None, str | None], int] = {}
        for old in sorted(tags, key=lambda item: (item["workspace_id"], item["id"])):
            if old["workspace_id"] not in workspace_ids:
                continue
            identity = (old["name"].casefold(), old["description"], old["color"])
            if old["id"] not in related_tag_ids and identity in equivalent_tags:
                tag_map[(user_id, old["id"])] = equivalent_tags[identity]
                continue
            name = _unique_name(old["name"], used_tag_names, 120)
            connection.execute(
                sa.text("""
                    INSERT INTO new_tags (id, user_id, name, description, color)
                    VALUES (:id, :user_id, :name, :description, :color)
                """),
                {
                    "id": next_tag_id,
                    "user_id": user_id,
                    "name": name,
                    "description": old["description"],
                    "color": old["color"],
                },
            )
            if old["id"] not in related_tag_ids:
                equivalent_tags[identity] = next_tag_id
            tag_map[(user_id, old["id"])] = next_tag_id
            next_tag_id += 1

    for old in tasks:
        user_id = old["created_by_user_id"]
        parent_id = old["parent_task_id"]
        if parent_id is not None and tasks_by_id[parent_id]["created_by_user_id"] != user_id:
            parent_id = None
        connection.execute(
            sa.text("""
                INSERT INTO new_tasks (
                    id, user_id, title, description, status_id, priority, due_date,
                    last_worked_at, finished_at, parent_task_id, created_at, updated_at
                ) VALUES (
                    :id, :user_id, :title, :description, :status_id, :priority, :due_date,
                    :last_worked_at, :finished_at, :parent_task_id, :created_at, :updated_at
                )
            """),
            {
                "id": old["id"],
                "user_id": user_id,
                "title": old["title"],
                "description": old["description"],
                "status_id": status_map[(user_id, old["status_id"])],
                "priority": old["priority"],
                "due_date": old["due_date"],
                "last_worked_at": old["last_worked_at"],
                "finished_at": old["finished_at"],
                "parent_task_id": parent_id,
                "created_at": old["created_at"],
                "updated_at": old["updated_at"],
            },
        )

    for old in task_tags:
        user_id = tasks_by_id[old["task_id"]]["created_by_user_id"]
        connection.execute(
            sa.text("""
                INSERT OR IGNORE INTO new_task_tags (task_id, tag_id)
                VALUES (:task_id, :tag_id)
            """),
            {"task_id": old["task_id"], "tag_id": tag_map[(user_id, old["tag_id"])]},
        )
    for user in users:
        user_id = user["id"]
        for old in tag_relationships:
            key = (user_id, old["child_tag_id"])
            if key not in tag_map:
                continue
            connection.execute(
                sa.text("""
                    INSERT OR IGNORE INTO new_tag_relationships (child_tag_id, parent_tag_id)
                    VALUES (:child_tag_id, :parent_tag_id)
                """),
                {
                    "child_tag_id": tag_map[key],
                    "parent_tag_id": tag_map[(user_id, old["parent_tag_id"])],
                },
            )

    for old in blocks:
        reason = old["reason"]
        blocker_id = old["blocking_task_id"]
        if blocker_id is not None:
            owner = tasks_by_id[old["task_id"]]["created_by_user_id"]
            if tasks_by_id[blocker_id]["created_by_user_id"] != owner:
                reason = f"Former blocking task: {tasks_by_id[blocker_id]['title']} (#{blocker_id})"
                blocker_id = None
        connection.execute(
            sa.text("""
                INSERT INTO new_task_blocks
                    (id, task_id, reason, blocked_at, unblocked_at, blocking_task_id)
                VALUES (:id, :task_id, :reason, :blocked_at, :unblocked_at, :blocking_task_id)
            """),
            {
                "id": old["id"],
                "task_id": old["task_id"],
                "reason": reason,
                "blocked_at": old["blocked_at"],
                "unblocked_at": old["unblocked_at"],
                "blocking_task_id": blocker_id,
            },
        )
    for old in sessions:
        user_id = old["user_id"]
        task_id = old["task_id"]
        if task_id is not None and tasks_by_id[task_id]["created_by_user_id"] != user_id:
            task_id = None
        connection.execute(
            sa.text("""
                INSERT INTO new_pomodoro_sessions
                    (user_id, tag_id, task_id, phase, state, short_breaks_taken, ends_at)
                VALUES (:user_id, :tag_id, :task_id, :phase, :state, :short_breaks_taken, :ends_at)
            """),
            {
                "user_id": user_id,
                "tag_id": tag_map[(user_id, old["tag_id"])] if old["tag_id"] is not None else None,
                "task_id": task_id,
                "phase": old["phase"],
                "state": old["state"],
                "short_breaks_taken": old["short_breaks_taken"],
                "ends_at": old["ends_at"],
            },
        )

    for table, expected in (
        ("new_tasks", len(tasks)),
        ("new_task_blocks", len(blocks)),
        ("new_pomodoro_sessions", len(sessions)),
    ):
        actual = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar()
        if actual != expected:
            raise RuntimeError(f"Migration changed the row count for {table}")

    for table in (
        "pomodoro_sessions",
        "task_assignees",
        "task_tags",
        "task_blocks",
        "tag_relationships",
        "tasks",
        "tags",
        "task_statuses",
        "workspace_members",
        "workspaces",
    ):
        op.drop_table(table)
    for table in (
        "task_statuses",
        "tags",
        "tasks",
        "task_tags",
        "tag_relationships",
        "task_blocks",
        "pomodoro_sessions",
    ):
        op.execute(f"ALTER TABLE new_{table} RENAME TO {table}")

    op.create_index("ix_task_statuses_user_id", "task_statuses", ["user_id"])
    op.create_index("ix_tags_user_id", "tags", ["user_id"])
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])
    op.create_index("ix_tasks_parent_task_id", "tasks", ["parent_task_id"])
    op.create_index("ix_tasks_status_id", "tasks", ["status_id"])
    op.create_index("ix_task_blocks_task_id", "task_blocks", ["task_id"])
    op.create_index("ix_task_blocks_blocking_task_id", "task_blocks", ["blocking_task_id"])
    op.create_index(
        "task_one_active_task_block",
        "task_blocks",
        ["task_id", "blocking_task_id"],
        unique=True,
        sqlite_where=sa.text("blocking_task_id IS NOT NULL AND unblocked_at IS NULL"),
    )

    violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(f"Foreign key violations after user migration: {violations[:5]}")
    connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    raise RuntimeError("Restore the pre-migration SQLite backup to return to workspaces")

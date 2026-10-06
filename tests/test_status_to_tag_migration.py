"""Protect existing tasks and their relationships during status removal."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def upgrade(database: Path, revision: str) -> None:
    environment = os.environ.copy()
    environment["NEXT_TASK_DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )


def test_status_migration_preserves_tasks_and_related_data(tmp_path: Path) -> None:
    database = tmp_path / "status-to-tags.sqlite3"
    upgrade(database, "f6c7a0d92e31")
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO users(id,email,display_name,password_hash) "
            "VALUES (1,'migration@example.com','Migration','x')"
        )
        connection.execute(
            "INSERT INTO workspaces(id,name,scoring_formula) "
            "VALUES (1,'Workspace','priority + statusValue * 20')"
        )
        connection.execute(
            "INSERT INTO workspace_members(user_id,workspace_id,role) VALUES (1,1,'owner')"
        )
        connection.execute(
            "INSERT INTO task_statuses(id,workspace_id,name,score_value) "
            "VALUES (1,1,'todo',0),(2,1,'doing',2)"
        )
        connection.execute(
            "INSERT INTO tags(id,workspace_id,name,color) VALUES (1,1,'todo','#123456')"
        )
        connection.execute(
            "INSERT INTO tasks(id,created_by_user_id,workspace_id,title,status_id,parent_task_id) "
            "VALUES (1,1,1,'First',1,NULL),(2,1,1,'Second',2,1)"
        )
        connection.execute("INSERT INTO task_tags(task_id,tag_id) VALUES (1,1)")
        connection.execute("INSERT INTO task_assignees(user_id,task_id) VALUES (1,2)")
        connection.execute("INSERT INTO task_blocks(id,task_id,reason) VALUES (1,1,'Waiting')")
        connection.execute(
            "INSERT INTO pomodoro_sessions"
            "(user_id,workspace_id,task_id,phase,state,short_breaks_taken) "
            "VALUES (1,1,2,'focus','ready',0)"
        )

    upgrade(database, "c4a1f593d078")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "c4a1f593d078",
        )
        assert connection.execute(
            "SELECT id,title,parent_task_id FROM tasks ORDER BY id"
        ).fetchall() == [(1, "First", None), (2, "Second", 1)]
        assert connection.execute(
            "SELECT id,name,score_value FROM tags ORDER BY id"
        ).fetchall() == [(1, "todo", 0), (2, "todo (status)", 0), (3, "doing", 2)]
        assert connection.execute(
            "SELECT task_id,tag_id FROM task_tags ORDER BY task_id,tag_id"
        ).fetchall() == [(1, 1), (1, 2), (2, 3)]
        assert connection.execute("SELECT user_id,task_id FROM task_assignees").fetchall() == [
            (1, 2)
        ]
        assert connection.execute("SELECT id,task_id,reason FROM task_blocks").fetchall() == [
            (1, 1, "Waiting")
        ]
        assert connection.execute("SELECT user_id,task_id FROM pomodoro_sessions").fetchall() == [
            (1, 2)
        ]
        assert connection.execute("SELECT scoring_formula FROM workspaces").fetchone() == (
            "priority + tagValue * 20",
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert "status_id" not in {
            column[1] for column in connection.execute("PRAGMA table_info(tasks)")
        }
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='task_statuses'"
            ).fetchone()
            is None
        )

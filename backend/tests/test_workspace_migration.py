"""Exercise the data migration against a populated pre-removal database."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD_REVISION = "e42a91c70d12"


def upgrade(path: Path, revision: str) -> None:
    environment = os.environ.copy()
    environment["NEXT_TASK_DATABASE_URL"] = f"sqlite:///{path.as_posix()}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def test_merge_preserves_tasks_and_history_without_cross_user_access(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    upgrade(path, OLD_REVISION)
    with sqlite3.connect(path) as db:
        db.executescript("""
            INSERT INTO users (id, email, display_name, password_hash)
              VALUES (1, 'one', 'One', 'hash'), (2, 'two', 'Two', 'hash');
            INSERT INTO workspaces (id, name, scoring_formula, created_at)
              VALUES (10, 'Old', 'priority * 10', '2025-01-01'),
                     (20, 'New', 'priority * 20', '2025-02-01');
            INSERT INTO workspace_members (user_id, workspace_id, role)
              VALUES (1, 10, 'owner'), (1, 20, 'owner'),
                     (2, 10, 'editor'), (2, 20, 'editor');
            INSERT INTO task_statuses (id, workspace_id, name, score_value)
              VALUES (101, 10, 'todo', 0), (102, 20, 'todo', 2);
            INSERT INTO tags (id, workspace_id, name, description, color)
              VALUES (201, 10, 'project', 'old', '#ff0000'),
                     (202, 20, 'project', 'new', '#0000ff');
            INSERT INTO tasks (id, created_by_user_id, workspace_id, title, status_id)
              VALUES (301, 1, 10, 'First', 101),
                     (302, 1, 20, 'Second', 102),
                     (303, 2, 20, 'Shared work', 102);
            UPDATE tasks SET parent_task_id = 301 WHERE id = 302;
            UPDATE tasks SET parent_task_id = 302 WHERE id = 303;
            INSERT INTO task_tags (task_id, tag_id)
              VALUES (301, 201), (302, 202), (303, 202);
            INSERT INTO tag_relationships (child_tag_id, parent_tag_id)
              VALUES (202, 201);
            INSERT INTO task_blocks (id, task_id, reason, blocking_task_id)
              VALUES (401, 301, NULL, 303), (402, 302, 'Waiting', NULL);
            INSERT INTO task_assignees (task_id, user_id) VALUES (301, 2);
            INSERT INTO pomodoro_sessions
              (user_id, workspace_id, tag_id, task_id, phase, state,
               short_breaks_taken)
              VALUES (1, 20, 202, 302, 'focus', 'ready', 0);
        """)
    upgrade(path, "head")
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        tasks = [
            dict(row)
            for row in db.execute(
                "SELECT id, user_id, title, parent_task_id FROM tasks ORDER BY id"
            )
        ]
        assert tasks == [
            {"id": 301, "user_id": 1, "title": "First", "parent_task_id": None},
            {"id": 302, "user_id": 1, "title": "Second", "parent_task_id": 301},
            {"id": 303, "user_id": 2, "title": "Shared work", "parent_task_id": None},
        ]
        assert db.execute("SELECT scoring_formula FROM users WHERE id=1").fetchone()[0] == (
            "priority * 10"
        )
        statuses = db.execute(
            "SELECT name, score_value FROM task_statuses WHERE user_id=1 ORDER BY id"
        ).fetchall()
        assert [(row[0], row[1]) for row in statuses] == [("todo", 0), ("todo (2)", 2)]
        tags = db.execute(
            "SELECT name, description FROM tags WHERE user_id=1 ORDER BY id"
        ).fetchall()
        assert [(row[0], row[1]) for row in tags] == [("project", "old"), ("project (2)", "new")]
        assert db.execute("SELECT COUNT(*) FROM task_tags").fetchone()[0] == 3
        assert db.execute("SELECT COUNT(*) FROM tag_relationships").fetchone()[0] == 2
        blocks = db.execute(
            "SELECT id, reason, blocking_task_id FROM task_blocks ORDER BY id"
        ).fetchall()
        assert [(row[0], row[2]) for row in blocks] == [(401, None), (402, None)]
        assert "Shared work" in blocks[0][1]
        assert blocks[1][1] == "Waiting"
        session_task_id = db.execute(
            "SELECT task_id FROM pomodoro_sessions WHERE user_id=1"
        ).fetchone()[0]
        assert session_task_id == 302
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            db.execute("SELECT name FROM sqlite_master WHERE name='workspaces'").fetchone() is None
        )

"""Keep existing tag relationships and task assignments when relaxing tag names."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


def test_tag_name_migration_preserves_data_and_allows_names_in_different_scopes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "tag-names.sqlite3"
    upgrade(path, "f3a91c7d2e40")
    with sqlite3.connect(path) as db:
        db.executescript("""
            INSERT INTO users (id, email, display_name, password_hash)
              VALUES (1, 'owner', 'Owner', 'hash');
            INSERT INTO tags (id, user_id, name)
              VALUES (1, 1, 'Work'), (2, 1, 'Personal'), (3, 1, 'Review');
            INSERT INTO tag_relationships (child_tag_id, parent_tag_id)
              VALUES (3, 1);
            INSERT INTO tasks (id, user_id, title)
              VALUES (10, 1, 'Check report');
            INSERT INTO task_tags (task_id, tag_id) VALUES (10, 3);
        """)
    upgrade(path, "head")
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("INSERT INTO tags (id, user_id, name) VALUES (4, 1, 'Review')")
        db.execute(
            "INSERT INTO tag_relationships (child_tag_id, parent_tag_id) VALUES (4, 2)"
        )
        assert db.execute("SELECT tag_id FROM task_tags WHERE task_id=10").fetchall() == [
            (3,)
        ]
        assert db.execute(
            "SELECT child_tag_id, parent_tag_id FROM tag_relationships ORDER BY child_tag_id"
        ).fetchall() == [(3, 1), (4, 2)]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []

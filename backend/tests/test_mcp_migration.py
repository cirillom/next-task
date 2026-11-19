import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_upgrade_preserves_data_and_ignores_obsolete_credentials(tmp_path: Path):
    path = tmp_path / "before-mcp.sqlite3"
    env = {**os.environ, "NEXT_TASK_DATABASE_URL": f"sqlite:///{path.as_posix()}"}

    def upgrade(revision):
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", revision],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            check=True,
            capture_output=True,
        )

    upgrade("c94e10635a27")
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO users (id, email, display_name, password_hash) "
            "VALUES (1, 'x', 'X', 'hash')"
        )
        db.execute("INSERT INTO tasks (user_id, title, priority) VALUES (1, 'Keep this', 1)")
        db.execute("CREATE TABLE mcp_tokens (token_hash TEXT)")
        db.execute("INSERT INTO mcp_tokens VALUES ('obsolete')")
    upgrade("head")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT title FROM tasks").fetchall() == [("Keep this",)]
        assert db.execute("SELECT token_hash FROM mcp_tokens").fetchall() == [("obsolete",)]
        assert db.execute("SELECT token_hash FROM mcp_credentials_v2").fetchall() == []

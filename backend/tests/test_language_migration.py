"""Language defaults must not rewrite content or invalidate pending account links."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_language_migration_preserves_existing_data(tmp_path: Path) -> None:
    path = tmp_path / "existing.sqlite3"
    environment = {**os.environ, "NEXT_TASK_DATABASE_URL": f"sqlite:///{path.as_posix()}"}

    def upgrade(revision: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", revision],
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )

    upgrade("b83d0f524916")
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO users (id, email, display_name, password_hash) "
            "VALUES (1, 'legacy-user', 'Name', 'hash')"
        )
        db.execute(
            "INSERT INTO tasks (user_id, title, description, due_date) "
            "VALUES (1, 'Não alterar', 'My notes', '2026-12-01')"
        )
        db.execute(
            "INSERT INTO invitations (email, token_hash, expires_at) "
            "VALUES ('new@example.com', 'keep-invite', '2027-01-01')"
        )
        db.execute(
            "INSERT INTO user_sessions (user_id, token_hash, expires_at) "
            "VALUES (1, 'keep-session', '2027-01-01')"
        )
    upgrade("head")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT email, password_hash, language FROM users").fetchall() == [
            ("legacy-user", "hash", "en")
        ]
        assert db.execute("SELECT title, description, due_date FROM tasks").fetchall() == [
            ("Não alterar", "My notes", "2026-12-01")
        ]
        assert db.execute("SELECT token_hash, language FROM invitations").fetchall() == [
            ("keep-invite", "en")
        ]
        assert db.execute("SELECT token_hash FROM user_sessions").fetchone() == ("keep-session",)

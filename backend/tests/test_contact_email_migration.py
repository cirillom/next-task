"""Verify that adding contact emails does not trust or alter legacy identifiers."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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


def test_existing_username_and_email_identifier_remain_unverified(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    upgrade(path, "c518b2d7e4f0")
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO users (email, display_name, password_hash) VALUES (?, ?, ?)",
            ("legacy-user", "Legacy", "hash"),
        )
        db.execute(
            "INSERT INTO users (email, display_name, password_hash) VALUES (?, ?, ?)",
            ("person@example.com", "Person", "hash"),
        )
    upgrade(path, "head")
    with sqlite3.connect(path) as db:
        rows = db.execute(
            "SELECT email, contact_email, contact_email_verified_at FROM users ORDER BY id"
        ).fetchall()
        assert rows == [("legacy-user", None, None), ("person@example.com", None, None)]
        assert db.execute("SELECT COUNT(*) FROM email_verifications").fetchone()[0] == 0

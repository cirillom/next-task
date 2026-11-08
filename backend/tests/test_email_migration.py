"""Preserve account data while upgrading to one verified account email."""

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
            "SELECT email, email_verified_at FROM users ORDER BY id"
        ).fetchall()
        assert rows == [("legacy-user", None), ("person@example.com", None)]
        assert db.execute("SELECT COUNT(*) FROM email_verifications").fetchone()[0] == 0


def test_upgrade_preserves_accounts_tasks_sessions_and_pending_links(tmp_path: Path) -> None:
    path = tmp_path / "verified.sqlite3"
    upgrade(path, "d8f7a20c6b41")
    verified_at = "2026-11-08 12:00:00"
    with sqlite3.connect(path) as db:
        db.executemany(
            "INSERT INTO users (id, email, display_name, password_hash, contact_email, "
            "contact_email_verified_at) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, "owner@example.com", "Owner", "hash", "owner@example.com", verified_at),
                (2, "legacy-user", "Legacy", "hash", "contact@example.com", verified_at),
            ],
        )
        db.execute("INSERT INTO tasks (user_id, title) VALUES (1, 'Keep this task')")
        db.execute(
            "INSERT INTO user_sessions (user_id, token_hash, expires_at) VALUES (1, ?, ?)",
            ("session-token-hash", "2027-01-01 00:00:00"),
        )
        db.execute(
            "INSERT INTO email_verifications "
            "(user_id, email, token_hash, expires_at, requested_at) "
            "VALUES (1, 'new@example.com', 'verification-token-hash', ?, ?)",
            ("2026-11-09 12:00:00", verified_at),
        )
    upgrade(path, "head")
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT email, email_verified_at FROM users ORDER BY id"
        ).fetchall() == [("owner@example.com", verified_at), ("legacy-user", None)]
        assert db.execute("SELECT user_id, title FROM tasks").fetchall() == [(1, "Keep this task")]
        assert db.execute("SELECT token_hash FROM user_sessions").fetchone() == (
            "session-token-hash",
        )
        assert db.execute(
            "SELECT email, token_hash FROM email_verifications"
        ).fetchone() == ("new@example.com", "verification-token-hash")
        assert "contact_email" not in {row[1] for row in db.execute("PRAGMA table_info(users)")}
        assert "requested_at" not in {
            row[1] for row in db.execute("PRAGMA table_info(email_verifications)")
        }
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []

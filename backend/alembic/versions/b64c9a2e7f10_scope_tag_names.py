"""Allow tags with the same name in different parent scopes.

Revision ID: b64c9a2e7f10
Revises: f3a91c7d2e40
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b64c9a2e7f10"
down_revision: str | None = "f3a91c7d2e40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "sqlite":
        raise RuntimeError("Tag name migration currently supports SQLite only")
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 0:
        raise RuntimeError("Stop all database writers before migrating tags")
    if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("Source database has broken foreign keys")

    op.execute("""
        CREATE TABLE new_tags (
            id INTEGER NOT NULL PRIMARY KEY, user_id INTEGER NOT NULL,
            name VARCHAR(120) NOT NULL, description TEXT, color VARCHAR(32),
            score_value FLOAT NOT NULL DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    op.execute("""
        INSERT INTO new_tags (id, user_id, name, description, color, score_value)
        SELECT id, user_id, name, description, color, score_value FROM tags
    """)
    op.drop_table("tags")
    op.rename_table("new_tags", "tags")
    op.create_index("ix_tags_user_id", "tags", ["user_id"])
    if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("Tag name migration broke foreign keys")
    connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    raise RuntimeError("Restore a pre-upgrade SQLite backup to restore global tag name uniqueness")

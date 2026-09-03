from app.database import engine
from sqlalchemy import text


def test_sqlite_foreign_keys_and_wal_are_enabled() -> None:
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert connection.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"

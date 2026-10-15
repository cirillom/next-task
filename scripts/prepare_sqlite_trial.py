"""Create an untouched backup and a separate SQLite trial database."""

import argparse
import json
import shutil
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()

    source = args.source.resolve(strict=True)
    if not source.is_file():
        parser.error("Source must be a SQLite database file")

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    run_dir = Path(__file__).resolve().parents[1] / "data" / "sqlite-trials" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    backup = run_dir / "before.sqlite3"
    trial_dir = run_dir / "trial"
    trial_dir.mkdir()
    trial = trial_dir / "next-task.sqlite3"

    with (
        closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as source_db,
        closing(sqlite3.connect(backup)) as backup_db,
    ):
        source_db.backup(backup_db)
        if backup_db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite backup integrity check failed")
    shutil.copy2(backup, trial)

    print(
        json.dumps(
            {
                "source": str(source),
                "backup": str(backup),
                "trial": str(trial),
                "trial_dir": str(trial_dir),
            }
        )
    )


if __name__ == "__main__":
    main()

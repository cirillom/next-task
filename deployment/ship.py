"""Merge a reviewed PR, publish a release, then update vmstudas."""

import argparse
import json
import subprocess
import time

REPO = "cirillom/next-task"
RELEASE_RUNS = [
    "gh", "run", "list", "--repo", REPO, "--workflow", "release.yml",
    "--event", "workflow_dispatch", "--branch", "main", "--limit", "1",
    "--json", "databaseId",
]
VM_UPDATE = (
    "cd /home/cirillo/services/next-task && "
    'test "$(/usr/bin/docker --context rootless compose config --images | sort -u)" '
    "= ghcr.io/cirillom/next-task:latest && "
    "/home/cirillo/.local/bin/next-task update && "
    "/usr/bin/docker --context rootless compose ps"
)


def latest_release_run() -> int | None:
    runs = json.loads(subprocess.check_output(RELEASE_RUNS, text=True))
    return runs[0]["databaseId"] if runs else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr", type=int, help="reviewed pull request number")
    parser.add_argument("bump", choices=("patch", "minor", "major"))
    args = parser.parse_args()
    if args.pr <= 0:
        parser.error("PR number must be positive")

    try:
        subprocess.run(["gh", "pr", "checks", str(args.pr), "--repo", REPO], check=True)
        previous = latest_release_run()
        subprocess.run(["gh", "pr", "merge", str(args.pr), "--repo", REPO, "--squash"], check=True)
        subprocess.run(
            ["gh", "workflow", "run", "release.yml", "--repo", REPO,
             "--ref", "main", "-f", f"bump={args.bump}"],
            check=True,
        )
        # shortcut: one release dispatcher at a time, add a correlation input if that changes.
        for _ in range(30):
            time.sleep(2)
            run_id = latest_release_run()
            if run_id is not None and run_id != previous:
                break
        else:
            parser.exit(1, "New release run not found; inspect GitHub Actions.\n")

        subprocess.run(
            ["gh", "run", "watch", str(run_id), "--repo", REPO, "--exit-status"], check=True
        )
        subprocess.run(["ssh", "vmstudas", VM_UPDATE], check=True)
    except subprocess.CalledProcessError as error:
        parser.exit(1, f"Stopped after failed command: {error.cmd}\n")


if __name__ == "__main__":
    main()

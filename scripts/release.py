"""Keep the Python and npm release metadata in sync using their package managers."""

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

VERSION_FILES = (
    "pyproject.toml",
    "uv.lock",
    "frontend/package.json",
    "frontend/package-lock.json",
)


def check_version(root: Path, tag: str | None = None) -> str:
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    lock = tomllib.loads((root / "uv.lock").read_text())
    packages = [package for package in lock["package"] if package["name"] == project["name"]]
    if len(packages) != 1 or packages[0].get("source") != {"editable": "."}:
        raise ValueError("uv.lock must contain exactly one editable root project")
    frontend = json.loads((root / "frontend/package.json").read_text())
    npm_lock = json.loads((root / "frontend/package-lock.json").read_text())
    versions = {
        "pyproject.toml": project["version"],
        "uv.lock": packages[0]["version"],
        "frontend/package.json": frontend["version"],
        "frontend/package-lock.json": npm_lock["version"],
        'frontend/package-lock.json packages[""]': npm_lock["packages"][""]["version"],
    }
    version = project["version"]
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        raise ValueError(f"Expected a stable major.minor.patch version, got {version!r}")
    if any(value != version for value in versions.values()):
        raise ValueError(f"Release versions differ: {versions}")
    if tag is not None and tag != f"v{version}":
        raise ValueError(f"Tag {tag!r} does not match v{version}")
    return version


def bump_version(root: Path, bump: str) -> str:
    if bump not in {"patch", "minor", "major"}:
        raise ValueError(f"Invalid version bump: {bump}")
    check_version(root)
    originals = {root / name: (root / name).read_bytes() for name in VERSION_FILES}
    try:
        subprocess.run(
            ["uv", "version", "--bump", bump, "--no-sync"],
            cwd=root,
            check=True,
            stdout=sys.stderr,
        )
        version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
        subprocess.run(
            ["npm", "version", version, "--no-git-tag-version", "--ignore-scripts"],
            cwd=root / "frontend",
            check=True,
            stdout=sys.stderr,
        )
        return check_version(root)
    except Exception:
        for path, content in originals.items():
            path.write_bytes(content)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Verify all release versions match")
    check.add_argument("--tag", help="Also require this exact vMAJOR.MINOR.PATCH tag")
    bump = commands.add_parser("bump", help="Update Python, npm, and both lockfiles")
    bump.add_argument("level", choices=("patch", "minor", "major"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        version = (
            check_version(root, args.tag)
            if args.command == "check"
            else bump_version(root, args.level)
        )
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Release error: {error}\n")
    print(version)


if __name__ == "__main__":
    main()

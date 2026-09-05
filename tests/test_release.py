"""Exercise the release CLI against isolated copies of the real package metadata."""

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VERSION_FILES = (
    "pyproject.toml",
    "uv.lock",
    "frontend/package.json",
    "frontend/package-lock.json",
)


@pytest.fixture
def project(tmp_path):
    for name in (*VERSION_FILES, "README.md", "scripts/release.py"):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, target)
    shutil.copytree(
        REPO / "backend/app", tmp_path / "backend/app", ignore=shutil.ignore_patterns("__pycache__")
    )
    return tmp_path


def run_release(project, *args, env=None):
    return subprocess.run(
        [sys.executable, str(project / "scripts/release.py"), *args],
        cwd=project,
        env={**os.environ, "UV_OFFLINE": "1", **(env or {})},
        text=True,
        capture_output=True,
    )


def snapshot(project):
    return {name: (project / name).read_bytes() for name in VERSION_FILES}


def test_check_is_read_only(project):
    before = snapshot(project)
    version = tomllib.loads(before["pyproject.toml"].decode())["project"]["version"]
    result = run_release(project, "check", "--tag", f"v{version}")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == version
    assert snapshot(project) == before


@pytest.mark.parametrize("level,index", [("major", 0), ("minor", 1), ("patch", 2)])
def test_bump_updates_all_metadata_without_changing_dependencies(project, level, index):
    before = tomllib.loads((project / "uv.lock").read_text())
    npm_before = json.loads((project / "frontend/package-lock.json").read_text())
    current = tomllib.loads((project / "pyproject.toml").read_text())["project"]["version"]
    parts = [int(part) for part in current.split(".")]
    parts[index] += 1
    parts[index + 1 :] = [0] * (2 - index)
    expected = ".".join(map(str, parts))

    result = run_release(project, "bump", level)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected
    assert run_release(project, "check", "--tag", f"v{expected}").returncode == 0

    after = tomllib.loads((project / "uv.lock").read_text())
    for package in before["package"]:
        if package["name"] == "next-task":
            package["version"] = expected
    assert after == before
    npm_before["version"] = expected
    npm_before["packages"][""]["version"] = expected
    assert json.loads((project / "frontend/package-lock.json").read_text()) == npm_before
    assert not (project / ".git").exists()


@pytest.mark.parametrize("target", ["python", "uv", "npm", "npm_lock", "npm_root"])
def test_mismatches_fail_before_any_bump(project, target):
    if target in {"python", "uv"}:
        name = "pyproject.toml" if target == "python" else "uv.lock"
        path = project / name
        content = path.read_text()
        if target == "python":
            data = tomllib.loads(content)["project"]
        else:
            data = next(p for p in tomllib.loads(content)["package"] if p["name"] == "next-task")
        old = 'name = "next-task"\nversion = "' + data["version"] + '"'
        assert old in content
        path.write_text(content.replace(old, 'name = "next-task"\nversion = "9.8.7"', 1))
    else:
        name = "frontend/package.json" if target == "npm" else "frontend/package-lock.json"
        path = project / name
        data = json.loads(path.read_text())
        entry = data["packages"][""] if target == "npm_root" else data
        entry["version"] = "9.8.7"
        path.write_text(json.dumps(data))
    before = snapshot(project)
    result = run_release(project, "bump", "patch")
    assert result.returncode != 0
    assert "Release versions differ" in result.stderr
    assert snapshot(project) == before


@pytest.mark.parametrize("tag", ["0.4.2", "v9.8.7", "v0.4.2-rc.1", "v01.2.3"])
def test_rejects_incorrect_tags(project, tag):
    result = run_release(project, "check", "--tag", tag)
    assert result.returncode != 0
    assert "does not match" in result.stderr


def test_npm_failure_restores_all_version_files(project):
    before = snapshot(project)
    bin_dir = project / "bin"
    bin_dir.mkdir()
    npm = bin_dir / "npm"
    npm.write_text("#!/bin/sh\necho npm-test-failure >&2\nexit 42\n")
    npm.chmod(0o755)
    result = run_release(project, "bump", "patch", env={"PATH": f"{bin_dir}:{os.environ['PATH']}"})
    assert result.returncode != 0
    assert "npm-test-failure" in result.stderr
    assert snapshot(project) == before


def test_invalid_bump_does_not_change_files(project):
    before = snapshot(project)
    result = run_release(project, "bump", "invalid")
    assert result.returncode != 0
    assert snapshot(project) == before

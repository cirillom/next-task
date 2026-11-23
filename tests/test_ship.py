"""The deployment command must stop before touching the VM when release fails."""

import json
import subprocess
import sys

import pytest

from deployment import ship


def test_ship_waits_for_release_before_vm_update(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    run_ids = iter((1, 2))
    monkeypatch.setattr(sys, "argv", ["ship.py", "100", "minor"])
    monkeypatch.setattr(ship.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        ship.subprocess,
        "check_output",
        lambda *_args, **_kwargs: json.dumps([{"databaseId": next(run_ids)}]),
    )

    def run(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        assert check
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(ship.subprocess, "run", run)
    ship.main()
    assert [command[:3] for command in calls] == [
        ["gh", "pr", "checks"],
        ["gh", "pr", "merge"],
        ["gh", "workflow", "run"],
        ["gh", "run", "watch"],
        ["ssh", "vmstudas", ship.VM_UPDATE],
    ]

    calls.clear()
    run_ids = iter((1, 2))

    def fail_release(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["gh", "run", "watch"]:
            raise subprocess.CalledProcessError(1, command)
        return run(command, check=check)

    monkeypatch.setattr(ship.subprocess, "run", fail_release)
    with pytest.raises(SystemExit):
        ship.main()
    assert not any(command[0] == "ssh" for command in calls)

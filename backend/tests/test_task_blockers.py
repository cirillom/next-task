from collections.abc import Callable

import pytest
from app.database import SessionLocal
from app.models import TaskBlock
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError


def test_task_blockers_share_history_and_resolve_when_blocker_finishes(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    workspace = client.post("/api/workspaces", json={"name": "Task blockers"}).json()
    status_id = client.get(f"/api/workspaces/{workspace['id']}/statuses").json()[0]["id"]

    def task(title: str) -> dict:
        response = client.post(
            "/api/tasks",
            json={
                "workspace_id": workspace["id"],
                "status_id": status_id,
                "title": title,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    first, second, target = task("First"), task("Second"), task("Target")

    for blocker in (first, second):
        response = client.post(
            f"/api/tasks/{target['id']}/block",
            json={
                "blocking_task_id": blocker["id"],
            },
        )
        assert response.status_code == 201, response.text
    manual = client.post(f"/api/tasks/{target['id']}/block", json={"reason": "Weather"})
    assert manual.status_code == 201, manual.text
    assert len(manual.json()["active_blocks"]) == 3
    assert {
        item["id"] for item in client.get(f"/api/tasks/{first['id']}").json()["blocks_tasks"]
    } == {target["id"]}
    assert client.post(f"/api/tasks/{target['id']}/unblock").status_code == 409
    assert (
        client.post(
            f"/api/tasks/{target['id']}/block", json={"blocking_task_id": first["id"]}
        ).status_code
        == 409
    )

    finished = client.post(f"/api/tasks/{first['id']}/finish")
    assert finished.status_code == 200, finished.text
    refreshed = client.get(f"/api/tasks/{target['id']}").json()
    assert len(refreshed["active_blocks"]) == 2
    first_entry = next(
        item for item in refreshed["blocking_history"] if item["blocking_task_id"] == first["id"]
    )
    assert first_entry["unblocked_at"] == finished.json()["finished_at"]
    assert client.post(f"/api/tasks/{first['id']}/reopen").status_code == 200
    assert len(client.get(f"/api/tasks/{target['id']}").json()["active_blocks"]) == 2

    remaining = next(
        item for item in refreshed["active_blocks"] if item["blocking_task_id"] == second["id"]
    )
    assert (
        client.post(f"/api/tasks/{target['id']}/blocks/{remaining['id']}/unblock").status_code
        == 200
    )
    assert (
        client.post(
            f"/api/tasks/{target['id']}/block", json={"blocking_task_id": first["id"]}
        ).status_code
        == 201
    )
    assert len(client.get(f"/api/tasks/{target['id']}").json()["blocking_history"]) == 4

    deleted = client.delete(f"/api/tasks/{first['id']}")
    assert deleted.status_code == 204, deleted.text
    refreshed = client.get(f"/api/tasks/{target['id']}").json()
    assert all(block["blocking_task_id"] != first["id"] for block in refreshed["blocking_history"])
    assert any(block["reason"] == "Deleted task: First" for block in refreshed["blocking_history"])
    assert client.delete(f"/api/workspaces/{workspace['id']}").status_code == 204


def test_task_block_validation_and_database_constraints(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    workspace = client.post("/api/workspaces", json={"name": "Block graph"}).json()
    status_id = client.get(f"/api/workspaces/{workspace['id']}/statuses").json()[0]["id"]

    def task(title: str, workspace_id: int = workspace["id"], status: int = status_id) -> int:
        response = client.post(
            "/api/tasks",
            json={
                "workspace_id": workspace_id,
                "status_id": status,
                "title": title,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    a, b, c = task("A"), task("B"), task("C")
    other = client.post("/api/workspaces", json={"name": "Other"}).json()
    other_status = client.get(f"/api/workspaces/{other['id']}/statuses").json()[0]["id"]
    foreign = task("Foreign", other["id"], other_status)

    def block(blocked: int, blocker: int):
        return client.post(f"/api/tasks/{blocked}/block", json={"blocking_task_id": blocker})

    assert block(a, a).status_code == 422
    assert block(a, foreign).status_code == 422
    assert (
        client.post(
            f"/api/tasks/{a}/block", json={"reason": "Both", "blocking_task_id": b}
        ).status_code
        == 422
    )
    assert client.post(f"/api/tasks/{a}/block", json={}).status_code == 422
    assert block(b, a).status_code == 201
    assert block(c, b).status_code == 201
    assert block(a, c).status_code == 422

    with SessionLocal() as db:
        db.add(TaskBlock(task_id=a, reason=None, blocking_task_id=None))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(TaskBlock(task_id=b, reason=None, blocking_task_id=a))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    assert client.post(f"/api/tasks/{a}/finish").status_code == 200
    assert block(c, a).status_code == 422

import runpy
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from app.database import SessionLocal, engine
from app.models import TaskBlock
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError


def make_task(client: TestClient) -> dict:
    workspace = client.post("/api/workspaces", json={"name": "Blocking"}).json()
    statuses = client.get(f"/api/workspaces/{workspace['id']}/statuses").json()
    response = client.post(
        "/api/tasks",
        json={
            "workspace_id": workspace["id"],
            "title": "Blocked task",
            "status_id": statuses[0]["id"],
        },
    )
    assert response.status_code == 201
    return response.json()


def assert_utc_timestamp(value: str) -> None:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)


def test_reblock_restores_existing_block_and_serializes_times_as_utc(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    task = make_task(client)

    blocked = client.post(
        f"/api/tasks/{task['id']}/block",
        json={"reason": "Waiting on hardware"},
    )
    assert blocked.status_code == 201
    original = blocked.json()["current_block"]
    assert_utc_timestamp(original["blocked_at"])

    unblocked = client.post(f"/api/tasks/{task['id']}/unblock")
    assert unblocked.status_code == 200
    inactive = unblocked.json()["blocking_history"][0]
    assert inactive["id"] == original["id"]
    assert inactive["unblocked_at"] is not None
    assert_utc_timestamp(inactive["unblocked_at"])

    reblocked = client.post(f"/api/tasks/{task['id']}/reblock")
    assert reblocked.status_code == 200
    body = reblocked.json()
    restored = body["current_block"]

    assert restored["id"] == original["id"]
    assert restored["reason"] == original["reason"]
    assert restored["blocked_at"] == original["blocked_at"]
    assert restored["unblocked_at"] is None
    assert len(body["blocking_history"]) == 1
    assert body["blocking_history"][0]["id"] == original["id"]
    assert body["blocking_history"][0]["unblocked_at"] is None

    already_blocked = client.post(f"/api/tasks/{task['id']}/reblock")
    assert already_blocked.status_code == 409


def test_delete_block_history_only_allows_inactive_entries(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    task = make_task(client)

    blocked = client.post(
        f"/api/tasks/{task['id']}/block",
        json={"reason": "Temporary blocker"},
    )
    assert blocked.status_code == 201
    block_id = blocked.json()["current_block"]["id"]

    active_delete = client.delete(f"/api/tasks/{task['id']}/blocks/{block_id}")
    assert active_delete.status_code == 409

    unblocked = client.post(f"/api/tasks/{task['id']}/unblock")
    assert unblocked.status_code == 200
    assert len(unblocked.json()["blocking_history"]) == 1

    deleted = client.delete(f"/api/tasks/{task['id']}/blocks/{block_id}")
    assert deleted.status_code == 200
    body = deleted.json()
    assert body["current_block"] is None
    assert body["blocking_history"] == []

    missing = client.delete(f"/api/tasks/{task['id']}/blocks/{block_id}")
    assert missing.status_code == 404


def test_scheduled_block_becomes_actionable_after_unblock_time(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    task = make_task(client)
    scheduled = datetime.now(UTC) + timedelta(hours=2)

    blocked = client.post(
        f"/api/tasks/{task['id']}/block",
        json={"reason": "Wait until later", "unblocked_at": scheduled.isoformat()},
    )
    assert blocked.status_code == 201
    body = blocked.json()
    assert body["current_block"] is not None
    original_block_id = body["current_block"]["id"]
    assert_utc_timestamp(body["current_block"]["unblocked_at"])

    workspace_id = task["workspace_id"]
    blocked_response = client.get(f"/api/tasks?workspace_id={workspace_id}&blocked=true")
    blocked_ids = {item["id"] for item in blocked_response.json()}
    actionable_response = client.get(f"/api/tasks?workspace_id={workspace_id}&blocked=false")
    actionable_ids = {item["id"] for item in actionable_response.json()}
    assert task["id"] in blocked_ids
    assert task["id"] not in actionable_ids

    with SessionLocal() as db:
        block = db.get(TaskBlock, original_block_id)
        assert block is not None
        block.unblocked_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()

    refreshed = client.get(f"/api/tasks/{task['id']}")
    assert refreshed.status_code == 200
    refreshed_body = refreshed.json()
    assert refreshed_body["current_block"] is None
    assert refreshed_body["blocking_history"][0]["unblocked_at"] is not None

    blocked_response = client.get(f"/api/tasks?workspace_id={workspace_id}&blocked=true")
    blocked_ids = {item["id"] for item in blocked_response.json()}
    actionable_response = client.get(f"/api/tasks?workspace_id={workspace_id}&blocked=false")
    actionable_ids = {item["id"] for item in actionable_response.json()}
    assert task["id"] not in blocked_ids
    assert task["id"] in actionable_ids

    next_schedule = datetime.now(UTC) + timedelta(hours=4)
    reblocked = client.post(
        f"/api/tasks/{task['id']}/reblock",
        json={"unblocked_at": next_schedule.isoformat()},
    )
    assert reblocked.status_code == 200
    reblocked_body = reblocked.json()
    restored = reblocked_body["current_block"]
    assert restored["id"] == original_block_id
    assert restored["reason"] == "Wait until later"
    assert_utc_timestamp(restored["unblocked_at"])
    assert len(reblocked_body["blocking_history"]) == 1


def test_auto_unblock_must_be_in_the_future(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    task = make_task(client)
    past = datetime.now(UTC) - timedelta(minutes=1)

    response = client.post(
        f"/api/tasks/{task['id']}/block",
        json={
            "reason": "Already expired",
            "unblocked_at": past.isoformat(),
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Auto-unblock time must be in the future"

    blocked = client.post(
        f"/api/tasks/{task['id']}/block",
        json={"reason": "Try again later"},
    )
    assert blocked.status_code == 201
    assert client.post(f"/api/tasks/{task['id']}/unblock").status_code == 200

    reblocked = client.post(
        f"/api/tasks/{task['id']}/reblock",
        json={"unblocked_at": past.isoformat()},
    )
    assert reblocked.status_code == 422
    assert reblocked.json()["detail"] == "Auto-unblock time must be in the future"


def test_database_trigger_rejects_two_scheduled_active_blocks(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    task = make_task(client)
    migration = runpy.run_path(
        "backend/alembic/versions/b71f3c9d4e20_enforce_scheduled_active_blocks.py"
    )

    with engine.begin() as connection:
        connection.exec_driver_sql(migration["INSERT_TRIGGER"])
        connection.exec_driver_sql(migration["UPDATE_TRIGGER"])

    with SessionLocal() as db:
        db.add(
            TaskBlock(
                task_id=task["id"],
                reason="First scheduled block",
                unblocked_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        db.commit()

        db.add(
            TaskBlock(
                task_id=task["id"],
                reason="Second scheduled block",
                unblocked_at=datetime.now(UTC) + timedelta(hours=2),
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

from collections.abc import Callable
from datetime import timedelta

from fastapi.testclient import TestClient


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
    from datetime import datetime

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

from collections.abc import Callable

from fastapi.testclient import TestClient


def test_draft_stays_out_of_normal_workflow_until_finalized(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    statuses = client.get("/api/statuses").json()

    created = client.post(
        "/api/drafts",
        json={
            "title": "Buy a new SSD",
            "description": "Compare 2 TB SATA and NVMe options",
        },
    )
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["priority"] == 0
    assert draft["status"]["id"] == statuses[0]["id"]
    assert draft["due_date"] is None
    assert draft["parent_task_id"] is None
    assert draft["direct_tags"] == []

    normal = client.get("/api/tasks", params={"finished": False})
    assert normal.status_code == 200
    assert draft["id"] not in {task["id"] for task in normal.json()}

    actionable = client.get(
        "/api/tasks",
        params={
            "finished": False,
            "blocked": False,
            "actionable": True,
        },
    )
    assert actionable.status_code == 200
    assert draft["id"] not in {task["id"] for task in actionable.json()}

    drafts = client.get("/api/drafts", params={})
    assert drafts.status_code == 200
    assert [task["id"] for task in drafts.json()] == [draft["id"]]

    assert client.post(f"/api/tasks/{draft['id']}/finish").status_code == 409
    assert (
        client.post(
            f"/api/tasks/{draft['id']}/block",
            json={"reason": "Not yet"},
        ).status_code
        == 409
    )

    finalized = client.patch(f"/api/tasks/{draft['id']}", json={"priority": 2})
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["priority"] == 2

    drafts_after = client.get("/api/drafts", params={}).json()
    assert drafts_after == []
    normal_after = client.get("/api/tasks", params={"finished": False}).json()
    assert draft["id"] in {task["id"] for task in normal_after}


def test_regular_task_api_cannot_create_priority_zero(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    statuses = client.get("/api/statuses").json()

    response = client.post(
        "/api/tasks",
        json={
            "title": "Not a draft",
            "status_id": statuses[0]["id"],
            "priority": 0,
        },
    )
    assert response.status_code == 422


def test_draft_can_store_and_update_full_task_metadata(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    statuses = client.get("/api/statuses").json()
    first_tag = client.post(
        "/api/tags",
        json={"name": "planning"},
    ).json()
    second_tag = client.post(
        "/api/tags",
        json={"name": "ready-later"},
    ).json()
    parent = client.post(
        "/api/tasks",
        json={
            "title": "Parent task",
            "status_id": statuses[0]["id"],
            "priority": 2,
        },
    ).json()

    created = client.post(
        "/api/drafts",
        json={
            "title": "Prepared draft",
            "description": "All details can be filled before activation.",
            "status_id": statuses[-1]["id"],
            "due_date": "2026-10-15",
            "last_worked_at": "2026-09-29T12:30:00Z",
            "parent_task_id": parent["id"],
            "tag_ids": [first_tag["id"]],
        },
    )
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["priority"] == 0
    assert draft["status"]["id"] == statuses[-1]["id"]
    assert draft["due_date"] == "2026-10-15"
    assert draft["last_worked_at"] is not None
    assert draft["parent_task_id"] == parent["id"]
    assert [tag["id"] for tag in draft["direct_tags"]] == [first_tag["id"]]

    updated = client.patch(
        f"/api/tasks/{draft['id']}",
        json={
            "title": "Prepared draft updated",
            "description": "Still a draft.",
            "status_id": statuses[0]["id"],
            "due_date": "2026-10-20",
            "parent_task_id": None,
            "tag_ids": [second_tag["id"]],
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["priority"] == 0
    assert body["title"] == "Prepared draft updated"
    assert body["description"] == "Still a draft."
    assert body["status"]["id"] == statuses[0]["id"]
    assert body["due_date"] == "2026-10-20"
    assert body["parent_task_id"] is None
    assert [tag["id"] for tag in body["direct_tags"]] == [second_tag["id"]]

    normal_ids = {
        task["id"] for task in client.get("/api/tasks", params={"finished": False}).json()
    }
    assert draft["id"] not in normal_ids
    draft_ids = {task["id"] for task in client.get("/api/drafts", params={}).json()}
    assert draft["id"] in draft_ids

    finalized = client.patch(f"/api/tasks/{draft['id']}", json={"priority": 3})
    assert finalized.status_code == 200
    assert finalized.json()["priority"] == 3
    assert draft["id"] not in {task["id"] for task in client.get("/api/drafts", params={}).json()}


def test_full_draft_creation_validates_task_relationships(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")

    response = client.post(
        "/api/drafts",
        json={
            "title": "Invalid status",
            "status_id": 999999,
        },
    )
    assert response.status_code == 422

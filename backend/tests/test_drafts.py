from collections.abc import Callable

from fastapi.testclient import TestClient


def test_draft_stays_out_of_normal_workflow_until_finalized(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    workspace = client.post("/api/workspaces", json={"name": "Drafts"}).json()
    statuses = client.get(f"/api/workspaces/{workspace['id']}/statuses").json()

    created = client.post(
        "/api/drafts",
        json={
            "workspace_id": workspace["id"],
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
    assert draft["assignees"] == []
    assert draft["direct_tags"] == []

    normal = client.get(
        "/api/tasks", params={"workspace_id": workspace["id"], "finished": False}
    )
    assert normal.status_code == 200
    assert draft["id"] not in {task["id"] for task in normal.json()}

    actionable = client.get(
        "/api/tasks",
        params={
            "workspace_id": workspace["id"],
            "finished": False,
            "blocked": False,
            "actionable": True,
        },
    )
    assert actionable.status_code == 200
    assert draft["id"] not in {task["id"] for task in actionable.json()}

    drafts = client.get("/api/drafts", params={"workspace_id": workspace["id"]})
    assert drafts.status_code == 200
    assert [task["id"] for task in drafts.json()] == [draft["id"]]

    assert client.post(f"/api/tasks/{draft['id']}/finish").status_code == 409
    assert client.post(
        f"/api/tasks/{draft['id']}/block",
        json={"reason": "Not yet"},
    ).status_code == 409

    finalized = client.patch(f"/api/tasks/{draft['id']}", json={"priority": 2})
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["priority"] == 2

    drafts_after = client.get("/api/drafts", params={"workspace_id": workspace["id"]}).json()
    assert drafts_after == []
    normal_after = client.get(
        "/api/tasks", params={"workspace_id": workspace["id"], "finished": False}
    ).json()
    assert draft["id"] in {task["id"] for task in normal_after}


def test_regular_task_api_cannot_create_priority_zero(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    workspace = client.post("/api/workspaces", json={"name": "Draft boundary"}).json()
    statuses = client.get(f"/api/workspaces/{workspace['id']}/statuses").json()

    response = client.post(
        "/api/tasks",
        json={
            "workspace_id": workspace["id"],
            "title": "Not a draft",
            "status_id": statuses[0]["id"],
            "priority": 0,
        },
    )
    assert response.status_code == 422

"""User ownership and core task flows after removing workspaces."""

from collections.abc import Callable

from fastapi.testclient import TestClient


def task(client: TestClient, title: str, **extra: object) -> dict:
    response = client.post("/api/tasks", json={"title": title, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_user_formula(logged_in_client: Callable[[str], TestClient]) -> None:
    client = logged_in_client("first-user@example.com")
    assert client.get("/api/settings/scoring").status_code == 200
    changed = client.put(
        "/api/settings/scoring", json={"scoring_formula": "priority * 10 + tagValue"}
    )
    assert changed.status_code == 200, changed.text
    assert client.get("/api/settings/scoring").json() == changed.json()
    assert (
        client.put(
            "/api/settings/scoring", json={"scoring_formula": "__import__('os')"}
        ).status_code
        == 422
    )


def test_user_tasks_share_one_ranked_queue(logged_in_client: Callable[[str], TestClient]) -> None:
    client = logged_in_client("queue-user@example.com")
    user_id = client.get("/api/auth/me").json()["id"]
    tag = client.post("/api/tags", json={"name": "project", "score_value": 3}).json()
    first = task(client, "First", tag_ids=[tag["id"]])
    second = task(client, "Second", parent_task_id=first["id"])
    assert first["user_id"] == second["user_id"] == user_id
    assert {item["id"] for item in client.get("/api/tasks").json()} == {first["id"], second["id"]}
    assert client.get(f"/api/tasks/{second['id']}").json()["parent_task_id"] == first["id"]
    assert client.get("/api/tags").json()[0]["score_value"] == 3


def test_user_boundaries_cover_tasks_tags_and_pomodoro(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("first@example.com")
    first_id = client.get("/api/auth/me").json()["id"]
    first_tag = client.post("/api/tags", json={"name": "private"}).json()
    first_task = task(client, "Private task", tag_ids=[first_tag["id"]])
    second = logged_in_client("second@example.com")
    second_id = second.get("/api/auth/me").json()["id"]
    assert first_id != second_id
    assert second.get("/api/tasks").json() == []
    assert second.get("/api/tags").json() == []
    assert second.get(f"/api/tasks/{first_task['id']}").status_code == 404
    assert (
        second.patch(f"/api/tasks/{first_task['id']}", json={"title": "Taken"}).status_code == 404
    )
    assert second.delete(f"/api/tasks/{first_task['id']}").status_code == 404
    assert second.patch(f"/api/tags/{first_tag['id']}", json={"name": "Taken"}).status_code == 404
    assert (
        second.post(
            "/api/tasks", json={"title": "Invalid tag", "tag_ids": [first_tag["id"]]}
        ).status_code
        == 422
    )
    assert (
        second.post(
            "/api/tasks", json={"title": "Invalid parent", "parent_task_id": first_task["id"]}
        ).status_code
        == 422
    )
    assert second.post("/api/pomodoro/session", json={"tag_id": first_tag["id"]}).status_code == 422
    assert (
        second.post("/api/pomodoro/session", json={"task_id": first_task["id"]}).status_code == 422
    )


def test_drafts_blocks_completion_and_focus_use_user_tasks(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("flows@example.com")
    draft = client.post("/api/drafts", json={"title": "Idea"})
    assert draft.status_code == 201, draft.text
    assert draft.json()["priority"] == 0
    assert [item["id"] for item in client.get("/api/drafts").json()] == [draft.json()["id"]]
    blocker = task(client, "Blocker")
    blocked = task(client, "Blocked")
    link = client.post(
        f"/api/tasks/{blocked['id']}/block", json={"blocking_task_id": blocker["id"]}
    )
    assert link.status_code == 201, link.text
    assert link.json()["current_block"]["blocking_task_id"] == blocker["id"]
    assert client.post(f"/api/tasks/{blocker['id']}/finish").status_code == 200
    assert client.get(f"/api/tasks/{blocked['id']}").json()["current_block"] is None
    session = client.post("/api/pomodoro/session", json={"task_id": blocked["id"]})
    assert session.status_code == 201, session.text
    assert session.json()["task_id"] == blocked["id"]

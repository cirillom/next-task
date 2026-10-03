"""User ownership and core task flows after removing workspaces."""

from app.main import app
from fastapi.testclient import TestClient


def signup(client: TestClient, name: str) -> int:
    response = client.post(
        "/api/auth/signup",
        json={"identifier": name, "password": "a secure password"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def task(client: TestClient, title: str, **extra: object) -> dict:
    response = client.post("/api/tasks", json={"title": title, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_signup_and_user_formula(client: TestClient) -> None:
    user_id = signup(client, "first-user")
    assert client.get("/api/auth/me").json()["id"] == user_id
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


def test_user_tasks_share_one_ranked_queue(client: TestClient) -> None:
    user_id = signup(client, "queue-user")
    tag = client.post("/api/tags", json={"name": "project", "score_value": 3}).json()
    first = task(client, "First", tag_ids=[tag["id"]])
    second = task(client, "Second", parent_task_id=first["id"])
    assert first["user_id"] == second["user_id"] == user_id
    assert {item["id"] for item in client.get("/api/tasks").json()} == {first["id"], second["id"]}
    assert client.get(f"/api/tasks/{second['id']}").json()["parent_task_id"] == first["id"]
    assert client.get("/api/tags").json()[0]["score_value"] == 3


def test_user_boundaries_cover_tasks_tags_and_pomodoro(client: TestClient) -> None:
    first_id = signup(client, "first")
    first_tag = client.post("/api/tags", json={"name": "private"}).json()
    first_task = task(client, "Private task", tag_ids=[first_tag["id"]])
    second = TestClient(app)
    second_id = signup(second, "second")
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


def test_drafts_blocks_completion_and_focus_use_user_tasks(client: TestClient) -> None:
    signup(client, "flows")
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

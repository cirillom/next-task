"""User ownership and core task flows."""

from app.main import app
from fastapi.testclient import TestClient


def signup(client: TestClient, name: str) -> tuple[int, int]:
    response = client.post(
        "/api/auth/signup",
        json={"identifier": name, "password": "a secure password"},
    )
    assert response.status_code == 201, response.text
    statuses = client.get("/api/statuses")
    assert statuses.status_code == 200
    assert [item["name"] for item in statuses.json()] == ["todo", "doing"]
    return response.json()["id"], statuses.json()[0]["id"]


def task(client: TestClient, status_id: int, title: str, **extra: object) -> dict:
    response = client.post("/api/tasks", json={"title": title, "status_id": status_id, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_signup_and_user_settings(client: TestClient) -> None:
    user_id, _ = signup(client, "first-user")
    assert client.get("/api/auth/me").json()["id"] == user_id
    assert client.get("/api/settings/scoring").status_code == 200
    changed = client.put(
        "/api/settings/scoring", json={"scoring_formula": "priority * 10 + statusValue"}
    )
    assert changed.status_code == 200, changed.text
    assert client.get("/api/settings/scoring").json() == changed.json()
    invalid = client.put("/api/settings/scoring", json={"scoring_formula": "__import__('os')"})
    assert invalid.status_code == 422


def test_user_tasks_share_one_queue(client: TestClient) -> None:
    user_id, todo_id = signup(client, "queue-user")
    another_status = client.post("/api/statuses", json={"name": "review", "score_value": 3})
    assert another_status.status_code == 201
    tag = client.post("/api/tags", json={"name": "project"})
    assert tag.status_code == 201, tag.text
    first = task(client, todo_id, "First", tag_ids=[tag.json()["id"]])
    second = task(client, another_status.json()["id"], "Second", parent_task_id=first["id"])
    assert first["user_id"] == second["user_id"] == user_id
    assert {item["id"] for item in client.get("/api/tasks").json()} == {first["id"], second["id"]}
    assert client.get(f"/api/tasks/{second['id']}").json()["parent_task_id"] == first["id"]
    assert [item["name"] for item in client.get("/api/tags").json()] == ["project"]


def test_user_boundaries_cover_tasks_statuses_tags_and_pomodoro(client: TestClient) -> None:
    first_id, first_status = signup(client, "first")
    first_tag = client.post("/api/tags", json={"name": "private"}).json()
    first_task = task(client, first_status, "Private task", tag_ids=[first_tag["id"]])
    second = TestClient(app)
    second_id, second_status = signup(second, "second")
    assert first_id != second_id
    assert first_status != second_status
    assert second.get("/api/tasks").json() == []
    assert second.get("/api/tags").json() == []
    assert second.get(f"/api/tasks/{first_task['id']}").status_code == 404
    assert (
        second.patch(f"/api/tasks/{first_task['id']}", json={"title": "Taken"}).status_code == 404
    )
    assert second.delete(f"/api/tasks/{first_task['id']}").status_code == 404
    assert second.patch(f"/api/statuses/{first_status}", json={"name": "Taken"}).status_code == 404
    assert second.patch(f"/api/tags/{first_tag['id']}", json={"name": "Taken"}).status_code == 404
    assert (
        second.post(
            "/api/tasks", json={"title": "Invalid status", "status_id": first_status}
        ).status_code
        == 422
    )
    assert (
        second.post(
            "/api/tasks",
            json={"title": "Invalid tag", "status_id": second_status, "tag_ids": [first_tag["id"]]},
        ).status_code
        == 422
    )
    assert (
        second.post(
            "/api/tasks",
            json={
                "title": "Invalid parent",
                "status_id": second_status,
                "parent_task_id": first_task["id"],
            },
        ).status_code
        == 422
    )
    assert second.post("/api/pomodoro/session", json={"tag_id": first_tag["id"]}).status_code == 422
    assert (
        second.post(
            "/api/pomodoro/session", json={"tag_id": None, "task_id": first_task["id"]}
        ).status_code
        == 422
    )


def test_drafts_blocks_completion_and_focus_use_user_tasks(client: TestClient) -> None:
    _, status_id = signup(client, "flows")
    draft = client.post("/api/drafts", json={"title": "Idea"})
    assert draft.status_code == 201, draft.text
    assert draft.json()["priority"] == 0
    assert [item["id"] for item in client.get("/api/drafts").json()] == [draft.json()["id"]]
    blocker = task(client, status_id, "Blocker")
    blocked = task(client, status_id, "Blocked")
    link = client.post(
        f"/api/tasks/{blocked['id']}/block", json={"blocking_task_id": blocker["id"]}
    )
    assert link.status_code == 201, link.text
    assert link.json()["current_block"]["blocking_task_id"] == blocker["id"]
    assert client.post(f"/api/tasks/{blocker['id']}/finish").status_code == 200
    assert client.get(f"/api/tasks/{blocked['id']}").json()["current_block"] is None
    session = client.post("/api/pomodoro/session", json={"tag_id": None, "task_id": blocked["id"]})
    assert session.status_code == 201, session.text
    assert session.json()["task_id"] == blocked["id"]


def test_status_deletion_rejects_in_use_status(client: TestClient) -> None:
    _, status_id = signup(client, "statuses")
    task(client, status_id, "Keep status")
    assert client.delete(f"/api/statuses/{status_id}").status_code == 409
    assert client.get("/api/statuses").status_code == 200

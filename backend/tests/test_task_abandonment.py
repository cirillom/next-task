from collections.abc import Callable

from app.database import SessionLocal
from app.models import Task
from app.pomodoro_models import PomodoroSession
from fastapi.testclient import TestClient


def create(client: TestClient, title: str, **values: object) -> dict:
    response = client.post("/api/tasks", json={"title": title, **values})
    assert response.status_code == 201, response.text
    return response.json()


def act(client: TestClient, task: dict, action: str) -> dict:
    response = client.post(f"/api/tasks/{task['id']}/{action}")
    assert response.status_code == 200, response.text
    return response.json()


def listed(client: TestClient, **params: object) -> set[int]:
    response = client.get("/api/tasks", params=params)
    assert response.status_code == 200, response.text
    return {task["id"] for task in response.json()}


def test_abandon_and_restore_preserve_task_data_and_blocking_history(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    tag = client.post("/api/tags", json={"name": "Keep this tag"}).json()
    task = create(
        client,
        "Keep this task",
        description="Keep **notes**",
        priority=7,
        due_date="2027-01-01",
        tag_ids=[tag["id"]],
    )
    blocked = client.post(
        f"/api/tasks/{task['id']}/block", json={"reason": "Waiting for information"}
    ).json()
    abandoned = act(client, task, "abandon")
    assert abandoned["abandoned_at"] is not None
    assert abandoned["abandoned_by_task_id"] == task["id"]
    assert abandoned["finished_at"] is None
    assert abandoned["score"] == abandoned["ranking_score"] == 0
    assert act(client, task, "abandon")["abandoned_at"] == abandoned["abandoned_at"]
    assert listed(client) == set()
    assert listed(client, abandoned="only") == {task["id"]}
    assert listed(client, abandoned="include", search="Keep", tag_id=tag["id"]) == {task["id"]}
    assert listed(client, abandoned="include", actionable=True) == set()
    restored = act(client, task, "restore")
    assert restored["abandoned_at"] is None
    assert restored["abandoned_by_task_id"] is None
    assert restored["score"] > 0
    for key in (
        "id",
        "title",
        "description",
        "priority",
        "due_date",
        "created_at",
        "last_worked_at",
        "direct_tags",
        "parent_task_id",
        "finished_at",
        "blocking_history",
        "active_blocks",
    ):
        assert restored[key] == blocked[key], key
    assert act(client, task, "restore")["abandoned_at"] is None


def test_parent_suppresses_descendants_and_preserves_separate_abandonment(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    parent = create(client, "Parent", priority=100)
    child = create(client, "Child", parent_task_id=parent["id"])
    grandchild = create(client, "Grandchild", parent_task_id=child["id"])
    separate = create(client, "Separately abandoned", parent_task_id=parent["id"])
    draft = client.post(
        "/api/drafts", json={"title": "Draft", "parent_task_id": parent["id"]}
    ).json()
    independent = act(client, separate, "abandon")
    act(client, parent, "abandon")
    assert listed(client) == set()
    assert listed(client, abandoned="only") == {
        parent["id"],
        child["id"],
        grandchild["id"],
        separate["id"],
    }
    assert client.get("/api/drafts").json() == []
    inherited = client.get(f"/api/tasks/{grandchild['id']}").json()
    assert inherited["abandoned_at"] is None
    assert inherited["abandoned_by_task_id"] == parent["id"]
    assert inherited["ranking_source_task_id"] is None
    # Restoring a child does not silently restore an abandoned ancestor.
    assert act(client, child, "restore")["abandoned_by_task_id"] == parent["id"]
    assert (
        client.put("/api/settings/scoring", json={"scoring_formula": "priority * 2"}).status_code
        == 200
    )
    assert client.patch(f"/api/tasks/{parent['id']}", json={"priority": 80}).status_code == 200
    act(client, parent, "restore")
    assert listed(client) == {parent["id"], child["id"], grandchild["id"]}
    assert {item["id"] for item in client.get("/api/drafts").json()} == {draft["id"]}
    remaining = client.get(f"/api/tasks/{separate['id']}").json()
    assert remaining["abandoned_at"] == independent["abandoned_at"]
    assert remaining["abandoned_by_task_id"] == separate["id"]
    assert listed(client, actionable=True) == {grandchild["id"]}
    ranked = client.get("/api/tasks?search=Grandchild").json()[0]
    assert ranked["ranking_source_task_id"] == parent["id"]
    assert ranked["ranking_score"] == 160


def test_abandoned_children_do_not_block_actionability_or_get_completed_with_parent(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    parent = create(client, "Parent")
    child = create(client, "Abandoned child", parent_task_id=parent["id"])
    grandchild = create(client, "Keep unfinished", parent_task_id=child["id"])
    act(client, child, "abandon")
    assert listed(client, actionable=True) == {parent["id"]}
    assert client.get(f"/api/tasks/{parent['id']}").json()["unfinished_descendant_count"] == 0
    assert client.post(f"/api/tasks/{child['id']}/finish").status_code == 409
    assert act(client, parent, "finish")["finished_at"] is not None
    for item in (child, grandchild):
        assert client.get(f"/api/tasks/{item['id']}").json()["finished_at"] is None
    act(client, child, "restore")
    assert listed(client, actionable=True) == {grandchild["id"]}


def test_abandoning_parent_resolves_descendant_dependencies(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    parent = create(client, "Project")
    blocker = create(client, "Blocker", parent_task_id=parent["id"])
    dependent = create(client, "Dependent")
    before = client.post(
        f"/api/tasks/{dependent['id']}/block", json={"blocking_task_id": blocker["id"]}
    ).json()
    act(client, parent, "abandon")
    after = client.get(f"/api/tasks/{dependent['id']}").json()
    assert after["active_blocks"] == []
    assert after["current_block"] is None
    assert after["last_worked_at"] == before["last_worked_at"]
    history = after["blocking_history"][0]
    assert history["id"] == before["current_block"]["id"]
    assert history["blocking_task_id"] == blocker["id"]
    assert history["unblocked_at"] is not None
    assert listed(client, blocked=False, actionable=True) == {dependent["id"]}
    for item in (parent, blocker):
        assert (
            client.post(
                f"/api/tasks/{dependent['id']}/block", json={"blocking_task_id": item["id"]}
            ).status_code
            == 422
        )
    act(client, parent, "restore")
    restored = client.get(f"/api/tasks/{dependent['id']}").json()
    assert restored["active_blocks"] == []
    assert restored["blocking_history"][0]["unblocked_at"] == history["unblocked_at"]


def test_abandonment_resolves_only_its_own_dependency_blocks(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    blocker = create(client, "Abandoned blocker")
    other = create(client, "Other blocker")
    dependent = create(client, "Dependent")
    for item in (blocker, other):
        assert (
            client.post(
                f"/api/tasks/{dependent['id']}/block", json={"blocking_task_id": item["id"]}
            ).status_code
            == 201
        )
    assert (
        client.post(
            f"/api/tasks/{dependent['id']}/block", json={"reason": "Still waiting"}
        ).status_code
        == 201
    )
    act(client, blocker, "abandon")
    after = client.get(f"/api/tasks/{dependent['id']}").json()
    assert len(after["active_blocks"]) == 2
    assert {block["blocking_task_id"] for block in after["active_blocks"]} == {other["id"], None}
    assert dependent["id"] not in listed(client, blocked=False, actionable=True)


def test_abandonment_clears_pinned_descendant_without_changing_timer(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    parent = create(client, "Parent")
    child = create(client, "Pinned child", parent_task_id=parent["id"])
    assert client.post("/api/pomodoro/session", json={"task_id": child["id"]}).status_code == 201
    running = client.post("/api/pomodoro/session/start").json()
    act(client, parent, "abandon")
    session = client.get("/api/pomodoro/session").json()
    assert session["task_id"] is None
    for key in ("phase", "state", "ends_at", "short_breaks_taken", "scope"):
        assert session[key] == running[key]
    assert (
        client.put("/api/pomodoro/session/task", json={"task_id": child["id"]}).status_code == 422
    )
    # Repair an old/stale pin as well, including one left by a concurrent selection.
    user_id = client.get("/api/auth/me").json()["id"]
    with SessionLocal() as db:
        db.get(PomodoroSession, user_id).task_id = child["id"]
        db.commit()
    assert client.get("/api/pomodoro/session").json()["task_id"] is None
    client.delete("/api/pomodoro/session")
    assert client.post("/api/pomodoro/session", json={"task_id": child["id"]}).status_code == 422
    act(client, parent, "restore")
    assert client.post("/api/pomodoro/session", json={"task_id": child["id"]}).status_code == 201


def test_moving_a_pinned_branch_under_abandoned_parent_clears_pin(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    abandoned = create(client, "Abandoned parent")
    parent = create(client, "Moving parent")
    child = create(client, "Pinned child", parent_task_id=parent["id"])
    dependent = create(client, "Dependent")
    client.post(f"/api/tasks/{dependent['id']}/block", json={"blocking_task_id": child["id"]})
    act(client, abandoned, "abandon")
    client.post("/api/pomodoro/session", json={"task_id": child["id"]})
    moved = client.patch(f"/api/tasks/{parent['id']}", json={"parent_task_id": abandoned["id"]})
    assert moved.status_code == 200, moved.text
    assert moved.json()["abandoned_by_task_id"] == abandoned["id"]
    assert client.get("/api/pomodoro/session").json()["task_id"] is None
    assert listed(client) == {dependent["id"]}
    assert client.get(f"/api/tasks/{dependent['id']}").json()["current_block"] is None
    assert (
        client.patch(f"/api/tasks/{parent['id']}", json={"parent_task_id": None}).status_code == 200
    )
    assert listed(client) == {parent["id"], child["id"], dependent["id"]}


def test_ownership_invalid_transitions_and_existing_completion_are_preserved(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    other = logged_in_client("other@example.com")
    task = create(client, "Private task")
    for action in ("abandon", "restore"):
        assert other.post(f"/api/tasks/{task['id']}/{action}").status_code == 404
    assert listed(other, abandoned="include") == set()
    completed = act(client, task, "finish")
    assert client.post(f"/api/tasks/{task['id']}/abandon").status_code == 409
    assert act(client, task, "restore")["finished_at"] == completed["finished_at"]
    draft = client.post("/api/drafts", json={"title": "Draft"}).json()
    assert client.post(f"/api/tasks/{draft['id']}/abandon").status_code == 409
    with SessionLocal() as db:
        assert db.get(Task, task["id"]).finished_at is not None

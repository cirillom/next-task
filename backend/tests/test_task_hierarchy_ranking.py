from collections.abc import Callable

from fastapi.testclient import TestClient


def make_workspace(client: TestClient) -> dict:
    workspace = client.post("/api/workspaces", json={"name": "Hierarchy ranking"}).json()
    return workspace


def make_task(
    client: TestClient,
    workspace: dict,
    title: str,
    priority: int,
    parent_task_id: int | None = None,
) -> dict:
    response = client.post(
        "/api/tasks",
        json={
            "workspace_id": workspace["id"],
            "title": title,
            "priority": priority,
            "parent_task_id": parent_task_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_parent_score_lifts_children_but_siblings_keep_own_score_order(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    workspace = make_workspace(client)

    parent = make_task(client, workspace, "Parent", priority=4)
    child_a = make_task(
        client,
        workspace,
        "Child A",
        priority=2,
        parent_task_id=parent["id"],
    )
    child_b = make_task(
        client,
        workspace,
        "Child B",
        priority=1,
        parent_task_id=parent["id"],
    )
    unrelated = make_task(client, workspace, "Unrelated", priority=3)

    tasks = client.get(
        "/api/tasks",
        params={"workspace_id": workspace["id"], "finished": False},
    ).json()

    assert [task["id"] for task in tasks] == [
        child_a["id"],
        child_b["id"],
        parent["id"],
        unrelated["id"],
    ]

    parent_read = next(task for task in tasks if task["id"] == parent["id"])
    child_a_read = next(task for task in tasks if task["id"] == child_a["id"])
    child_b_read = next(task for task in tasks if task["id"] == child_b["id"])

    assert child_a_read["score"] > child_b_read["score"]
    assert child_a_read["ranking_score"] == parent_read["score"]
    assert child_b_read["ranking_score"] == parent_read["score"]
    assert child_a_read["ranking_source_task_id"] == parent["id"]
    assert child_b_read["ranking_source_task_id"] == parent["id"]
    assert child_a_read["ranking_source_score"] == parent_read["score"]
    assert child_b_read["ranking_source_score"] == parent_read["score"]
    assert parent_read["ranking_source_task_id"] is None


def test_hierarchy_ranking_does_not_force_low_score_family_above_unrelated_work(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    workspace = make_workspace(client)

    parent = make_task(client, workspace, "Low parent", priority=1)
    important = make_task(
        client,
        workspace,
        "Important child",
        priority=5,
        parent_task_id=parent["id"],
    )
    minor = make_task(
        client,
        workspace,
        "Minor child",
        priority=1,
        parent_task_id=parent["id"],
    )
    unrelated = make_task(client, workspace, "Unrelated", priority=3)

    tasks = client.get(
        "/api/tasks",
        params={"workspace_id": workspace["id"], "finished": False},
    ).json()

    assert [task["id"] for task in tasks] == [
        important["id"],
        unrelated["id"],
        minor["id"],
        parent["id"],
    ]


def test_actionable_ranking_uses_parent_boost_without_changing_own_score(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    workspace = make_workspace(client)

    parent = make_task(client, workspace, "Urgent parent", priority=4)
    child = make_task(
        client,
        workspace,
        "Low child",
        priority=1,
        parent_task_id=parent["id"],
    )
    unrelated = make_task(client, workspace, "Unrelated", priority=3)

    tasks = client.get(
        "/api/tasks",
        params={
            "workspace_id": workspace["id"],
            "finished": False,
            "blocked": False,
            "actionable": True,
        },
    ).json()

    assert [task["id"] for task in tasks] == [child["id"], unrelated["id"]]
    child_read, unrelated_read = tasks
    parent_read = client.get(f"/api/tasks/{parent['id']}").json()
    assert child_read["score"] < unrelated_read["score"]
    assert child_read["ranking_score"] == parent_read["score"]
    assert child_read["ranking_source_task_id"] == parent["id"]
    assert child_read["ranking_source_score"] == parent_read["score"]
    assert unrelated_read["ranking_score"] == unrelated_read["score"]

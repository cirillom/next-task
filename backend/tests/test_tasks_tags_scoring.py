from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pytest
from app.database import SessionLocal
from app.models import Task
from app.services.scoring import DEFAULT_SCORING_FORMULA, FormulaError, evaluate_formula, score_task
from fastapi.testclient import TestClient


def make_workspace(client: TestClient, name: str = "Tasks") -> tuple[dict, list[dict]]:
    workspace = client.post("/api/workspaces", json={"name": name}).json()
    statuses = client.get(f"/api/workspaces/{workspace['id']}/statuses").json()
    return workspace, statuses


def make_task(
    client: TestClient,
    workspace: dict,
    statuses: list[dict],
    title: str = "A task",
    **values: object,
) -> dict:
    payload = {
        "workspace_id": workspace["id"],
        "title": title,
        "status_id": statuses[0]["id"],
        **values,
    }
    response = client.post("/api/tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_assignee_must_belong_to_task_workspace(
    logged_in_client: Callable[[str], TestClient],
    create_user: Callable,
) -> None:
    client = logged_in_client("owner@example.com")
    outsider = create_user("outsider@example.com")
    workspace, statuses = make_workspace(client)

    response = client.post(
        "/api/tasks",
        json={
            "workspace_id": workspace["id"],
            "title": "Invalid assignment",
            "status_id": statuses[0]["id"],
            "assignee_ids": [outsider.id],
        },
    )
    assert response.status_code == 422

    client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"email": outsider.email, "role": "editor"},
    )
    valid = make_task(client, workspace, statuses, "Valid assignment", assignee_ids=[outsider.id])
    assert [user["id"] for user in valid["assignees"]] == [outsider.id]
    removal = client.delete(f"/api/workspaces/{workspace['id']}/members/{outsider.id}")
    assert removal.status_code == 409


def test_task_hierarchy_rejects_self_cycles_and_cross_workspace_parents(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    workspace, statuses = make_workspace(client)
    other_workspace, other_statuses = make_workspace(client, "Other")
    first = make_task(client, workspace, statuses, "First")
    second = make_task(client, workspace, statuses, "Second", parent_task_id=first["id"])
    other = make_task(client, other_workspace, other_statuses, "Other")

    self_parent = client.patch(f"/api/tasks/{first['id']}", json={"parent_task_id": first["id"]})
    assert self_parent.status_code == 422
    cycle = client.patch(f"/api/tasks/{first['id']}", json={"parent_task_id": second["id"]})
    assert cycle.status_code == 422
    cross_workspace = client.patch(
        f"/api/tasks/{first['id']}", json={"parent_task_id": other["id"]}
    )
    assert cross_workspace.status_code == 422


def test_tag_dag_and_inherited_filtering(logged_in_client: Callable[[str], TestClient]) -> None:
    client = logged_in_client("owner@example.com")
    workspace, statuses = make_workspace(client)
    tags = {}
    for name in ("next-task", "projects", "programming"):
        response = client.post(f"/api/workspaces/{workspace['id']}/tags", json={"name": name})
        assert response.status_code == 201
        tags[name] = response.json()

    first_edge = client.post(
        f"/api/workspaces/{workspace['id']}/tags/{tags['next-task']['id']}/parents",
        json={"parent_tag_id": tags["projects"]["id"]},
    )
    assert first_edge.status_code == 201
    second_edge = client.post(
        f"/api/workspaces/{workspace['id']}/tags/{tags['projects']['id']}/parents",
        json={"parent_tag_id": tags["programming"]["id"]},
    )
    assert second_edge.status_code == 201
    cycle = client.post(
        f"/api/workspaces/{workspace['id']}/tags/{tags['programming']['id']}/parents",
        json={"parent_tag_id": tags["next-task"]["id"]},
    )
    assert cycle.status_code == 422

    task = make_task(
        client,
        workspace,
        statuses,
        tag_ids=[tags["next-task"]["id"]],
    )
    assert [tag["name"] for tag in task["direct_tags"]] == ["next-task"]
    assert {tag["name"] for tag in task["inherited_tags"]} == {
        "projects",
        "programming",
    }
    matches = client.get(
        "/api/tasks",
        params={"workspace_id": workspace["id"], "tag_id": tags["programming"]["id"]},
    ).json()
    assert [item["id"] for item in matches] == [task["id"]]


def test_finish_and_reopen_are_independent_from_status(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    workspace, statuses = make_workspace(client)
    task = make_task(client, workspace, statuses)

    finished = client.post(f"/api/tasks/{task['id']}/finish").json()
    assert finished["finished_at"] is not None
    assert finished["status"]["id"] == task["status"]["id"]
    queue = client.get("/api/tasks", params={"workspace_id": workspace["id"]}).json()
    assert queue == []

    reopened = client.post(f"/api/tasks/{task['id']}/reopen").json()
    assert reopened["finished_at"] is None
    assert reopened["status"]["id"] == task["status"]["id"]


def test_only_one_active_block_and_repeated_history(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    workspace, statuses = make_workspace(client)
    task = make_task(client, workspace, statuses)

    blocked = client.post(f"/api/tasks/{task['id']}/block", json={"reason": "Waiting on hardware"})
    assert blocked.status_code == 201
    assert blocked.json()["current_block"]["reason"] == "Waiting on hardware"
    duplicate = client.post(f"/api/tasks/{task['id']}/block", json={"reason": "Another reason"})
    assert duplicate.status_code == 409

    assert client.post(f"/api/tasks/{task['id']}/unblock").status_code == 200
    again = client.post(f"/api/tasks/{task['id']}/block", json={"reason": "Waiting again"})
    assert again.status_code == 201
    body = again.json()
    assert body["current_block"]["reason"] == "Waiting again"
    assert len(body["blocking_history"]) == 2
    assert body["blocking_history"][1]["unblocked_at"] is not None


def test_score_calculation_and_safe_formula(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    values = {
        "priority": 2.0,
        "ageDays": 10.0,
        "idleDays": 5.0,
        "dueOffsetDays": 3.0,
        "hasDueDate": 1.0,
        "statusValue": 1.0,
    }
    assert evaluate_formula("priority * 20 + ageDays + statusValue", values) == 51
    assert evaluate_formula("100 if dueOffsetDays > 0 else 0", values) == 100
    assert evaluate_formula("exp(0)", values) == 1
    with pytest.raises(FormulaError):
        evaluate_formula("__import__('os').system('id')", values)
    with pytest.raises(FormulaError):
        evaluate_formula("sqrt(4)", values)

    no_due_date = {
        "priority": 1.0,
        "ageDays": 0.0,
        "idleDays": 0.0,
        "dueOffsetDays": 0.0,
        "hasDueDate": 0.0,
        "statusValue": 0.0,
    }
    assert evaluate_formula(DEFAULT_SCORING_FORMULA, no_due_date) == 25

    due_today = {**no_due_date, "hasDueDate": 1.0}
    assert evaluate_formula(DEFAULT_SCORING_FORMULA, due_today) == 75

    due_in_seven_days = {**due_today, "dueOffsetDays": -7.0}
    assert evaluate_formula(DEFAULT_SCORING_FORMULA, due_in_seven_days) == pytest.approx(
        25 + 50 / 2.718281828459045
    )

    client = logged_in_client("owner@example.com")
    workspace, statuses = make_workspace(client)
    task_data = make_task(client, workspace, statuses, priority=3)
    with SessionLocal() as db:
        task = db.get(Task, task_data["id"])
        assert task is not None
        task.created_at = datetime.now(UTC) - timedelta(days=10)
        task.last_worked_at = datetime.now(UTC) - timedelta(days=4)
        task.due_date = date.today() - timedelta(days=2)
        db.commit()
        assert score_task(task, datetime.now(UTC)) == pytest.approx(171.5, abs=0.1)

    invalid = client.patch(
        f"/api/workspaces/{workspace['id']}",
        json={"scoring_formula": "open('/etc/passwd').read()"},
    )
    assert invalid.status_code == 422

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


@pytest.mark.parametrize(
    "timestamp",
    ["2026-09-09T14:30:00-03:00", "2026-09-09T23:00:00+05:30", "2026-09-09T17:30:00"],
)
def test_timestamps_round_trip_as_utc_without_shifting_due_dates(
    logged_in_client: Callable[[str], TestClient], timestamp: str,
) -> None:
    client = logged_in_client("owner@example.com")
    workspace, statuses = make_workspace(client)
    task = make_task(
        client, workspace, statuses, last_worked_at=timestamp, due_date="2026-09-09"
    )
    expected = datetime(2026, 9, 9, 17, 30, tzinfo=UTC)

    def assert_utc_timestamps(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("_at") and item is not None:
                    assert datetime.fromisoformat(item).utcoffset() == timedelta(0), (key, item)
                assert_utc_timestamps(item)
        elif isinstance(value, list):
            for item in value:
                assert_utc_timestamps(item)

    assert_utc_timestamps(workspace)
    assert_utc_timestamps(client.get("/api/auth/me").json())
    assert_utc_timestamps(task)
    assert datetime.fromisoformat(task["last_worked_at"]) == expected
    fetched = client.get(f"/api/tasks/{task['id']}").json()
    assert datetime.fromisoformat(fetched["last_worked_at"]) == expected
    assert fetched["due_date"] == "2026-09-09"
    updated = client.patch(f"/api/tasks/{task['id']}", json={"last_worked_at": timestamp})
    assert updated.status_code == 200, updated.text
    assert datetime.fromisoformat(updated.json()["last_worked_at"]) == expected
    assert_utc_timestamps(updated.json())
    cleared = client.patch(f"/api/tasks/{task['id']}", json={"last_worked_at": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["last_worked_at"] is None


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

    assert second["parent_task"] == {
        "id": first["id"],
        "title": "First",
        "finished_at": None,
        "unfinished_descendant_count": 1,
    }

    self_parent = client.patch(f"/api/tasks/{first['id']}", json={"parent_task_id": first["id"]})
    assert self_parent.status_code == 422
    cycle = client.patch(f"/api/tasks/{first['id']}", json={"parent_task_id": second["id"]})
    assert cycle.status_code == 422
    cross_workspace = client.patch(
        f"/api/tasks/{first['id']}", json={"parent_task_id": other["id"]}
    )
    assert cross_workspace.status_code == 422


def test_finishing_parent_cascades_and_reopening_child_reopens_ancestors(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    workspace, statuses = make_workspace(client)
    parent = make_task(client, workspace, statuses, "Parent")
    child = make_task(client, workspace, statuses, "Child", parent_task_id=parent["id"])
    grandchild = make_task(
        client,
        workspace,
        statuses,
        "Grandchild",
        parent_task_id=child["id"],
    )

    parent_before = client.get(f"/api/tasks/{parent['id']}").json()
    child_before = client.get(f"/api/tasks/{child['id']}").json()
    assert parent_before["unfinished_descendant_count"] == 2
    assert child_before["unfinished_descendant_count"] == 1
    assert parent_before["subtasks"][0]["unfinished_descendant_count"] == 1

    finished_parent = client.post(f"/api/tasks/{parent['id']}/finish").json()
    assert finished_parent["finished_at"] is not None
    assert finished_parent["unfinished_descendant_count"] == 0
    assert finished_parent["subtasks"][0]["finished_at"] is not None
    assert client.get(f"/api/tasks/{child['id']}").json()["finished_at"] is not None
    assert client.get(f"/api/tasks/{grandchild['id']}").json()["finished_at"] is not None

    reopened_grandchild = client.post(f"/api/tasks/{grandchild['id']}/reopen").json()
    assert reopened_grandchild["finished_at"] is None
    assert client.get(f"/api/tasks/{child['id']}").json()["finished_at"] is None
    reopened_parent = client.get(f"/api/tasks/{parent['id']}").json()
    assert reopened_parent["finished_at"] is None
    assert reopened_parent["unfinished_descendant_count"] == 2


def test_actionable_tasks_are_leaf_tasks_for_current_user_or_unassigned(
    logged_in_client: Callable[[str], TestClient],
    create_user: Callable,
) -> None:
    client = logged_in_client("owner@example.com")
    owner_id = client.get("/api/auth/me").json()["id"]
    teammate = create_user("teammate@example.com")
    workspace, statuses = make_workspace(client)
    client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"email": teammate.email, "role": "editor"},
    )

    parent = make_task(client, workspace, statuses, "Project container")
    child = make_task(
        client,
        workspace,
        statuses,
        "Concrete next action",
        parent_task_id=parent["id"],
    )
    mine = make_task(client, workspace, statuses, "Mine", assignee_ids=[owner_id])
    shared = make_task(
        client,
        workspace,
        statuses,
        "Shared",
        assignee_ids=[owner_id, teammate.id],
    )
    theirs = make_task(client, workspace, statuses, "Theirs", assignee_ids=[teammate.id])
    unassigned = make_task(client, workspace, statuses, "Unassigned")

    normal_ids = {
        item["id"]
        for item in client.get(
            "/api/tasks", params={"workspace_id": workspace["id"], "finished": False}
        ).json()
    }
    assert parent["id"] in normal_ids
    assert theirs["id"] in normal_ids

    actionable = client.get(
        "/api/tasks",
        params={
            "workspace_id": workspace["id"],
            "finished": False,
            "blocked": False,
            "actionable": True,
        },
    ).json()
    actionable_ids = {item["id"] for item in actionable}
    assert child["id"] in actionable_ids
    assert mine["id"] in actionable_ids
    assert shared["id"] in actionable_ids
    assert unassigned["id"] in actionable_ids
    assert parent["id"] not in actionable_ids
    assert theirs["id"] not in actionable_ids

    assert client.post(f"/api/tasks/{child['id']}/finish").status_code == 200
    actionable_after_finish = client.get(
        "/api/tasks",
        params={
            "workspace_id": workspace["id"],
            "finished": False,
            "blocked": False,
            "actionable": True,
        },
    ).json()
    actionable_after_finish_ids = {item["id"] for item in actionable_after_finish}
    assert parent["id"] in actionable_after_finish_ids
    assert child["id"] not in actionable_after_finish_ids


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

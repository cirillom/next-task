from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pytest
from app.database import SessionLocal
from app.models import Task
from app.services.scoring import DEFAULT_SCORING_FORMULA, FormulaError, evaluate_formula, score_task
from fastapi.testclient import TestClient


def statuses_for(client: TestClient) -> list[dict]:
    return client.get("/api/statuses").json()


def make_task(
    client: TestClient,
    statuses: list[dict],
    title: str = "A task",
    **values: object,
) -> dict:
    payload = {
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
    logged_in_client: Callable[[str], TestClient],
    timestamp: str,
) -> None:
    client = logged_in_client("owner@example.com")
    statuses = statuses_for(client)
    task = make_task(client, statuses, last_worked_at=timestamp, due_date="2026-09-09")
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


def test_status_must_belong_to_task_user(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    outsider = logged_in_client("outsider@example.com")
    statuses = statuses_for(client)
    owner_id = client.get("/api/auth/me").json()["id"]
    response = outsider.post(
        "/api/tasks",
        json={
            "title": "Invalid status",
            "status_id": statuses[0]["id"],
        },
    )
    assert response.status_code == 422
    assert make_task(client, statuses, "Valid task")["user_id"] == owner_id


def test_task_hierarchy_rejects_self_cycles_and_cross_user_parents(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    statuses = statuses_for(client)
    other_client = logged_in_client("other@example.com")
    other_statuses = statuses_for(other_client)
    first = make_task(client, statuses, "First")
    second = make_task(client, statuses, "Second", parent_task_id=first["id"])
    other = make_task(other_client, other_statuses, "Other")

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
    cross_user = client.patch(f"/api/tasks/{first['id']}", json={"parent_task_id": other["id"]})
    assert cross_user.status_code == 422

    detached = client.patch(f"/api/tasks/{second['id']}", json={"parent_task_id": None})
    assert detached.status_code == 200
    assert detached.json()["parent_task"] is None
    assert client.get(f"/api/tasks/{first['id']}").json()["subtasks"] == []
    assert client.get(f"/api/tasks/{second['id']}").status_code == 200


def test_finishing_parent_cascades_and_reopening_child_reopens_ancestors(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    statuses = statuses_for(client)
    parent = make_task(client, statuses, "Parent")
    child = make_task(client, statuses, "Child", parent_task_id=parent["id"])
    grandchild = make_task(
        client,
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


def test_actionable_tasks_are_leaf_tasks_for_current_user(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    statuses = statuses_for(client)

    parent = make_task(client, statuses, "Project container")
    child = make_task(
        client,
        statuses,
        "Concrete next action",
        parent_task_id=parent["id"],
    )
    mine = make_task(client, statuses, "Mine")
    shared = make_task(client, statuses, "Shared")
    other_client = logged_in_client("other@example.com")
    other_statuses = statuses_for(other_client)
    theirs = make_task(other_client, other_statuses, "Theirs")
    unassigned = make_task(client, statuses, "Another")

    normal_ids = {
        item["id"] for item in client.get("/api/tasks", params={"finished": False}).json()
    }
    assert parent["id"] in normal_ids
    assert theirs["id"] not in normal_ids

    actionable = client.get(
        "/api/tasks",
        params={
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
    statuses = statuses_for(client)
    tags = {}
    for name in ("next-task", "projects", "programming"):
        response = client.post("/api/tags", json={"name": name})
        assert response.status_code == 201
        tags[name] = response.json()

    first_edge = client.post(
        f"/api/tags/{tags['next-task']['id']}/parents",
        json={"parent_tag_id": tags["projects"]["id"]},
    )
    assert first_edge.status_code == 201
    second_edge = client.post(
        f"/api/tags/{tags['projects']['id']}/parents",
        json={"parent_tag_id": tags["programming"]["id"]},
    )
    assert second_edge.status_code == 201
    cycle = client.post(
        f"/api/tags/{tags['programming']['id']}/parents",
        json={"parent_tag_id": tags["next-task"]["id"]},
    )
    assert cycle.status_code == 422

    task = make_task(
        client,
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
        params={"tag_id": tags["programming"]["id"]},
    ).json()
    assert [item["id"] for item in matches] == [task["id"]]

    usage = {tag["name"]: tag["direct_task_count"] for tag in client.get("/api/tags").json()}
    assert usage == {"next-task": 1, "programming": 0, "projects": 0}

    make_task(
        client,
        statuses,
        "Direct project task",
        tag_ids=[tags["projects"]["id"]],
    )
    usage = {tag["name"]: tag["direct_task_count"] for tag in client.get("/api/tags").json()}
    assert usage == {"next-task": 1, "programming": 0, "projects": 1}


def test_multi_tag_filters_support_all_any_exclude_and_other_filters(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    statuses = statuses_for(client)

    tags: dict[str, dict] = {}
    for name in ("project", "homelab", "server", "research", "shopping", "personal"):
        response = client.post(
            "/api/tags",
            json={"name": name},
        )
        assert response.status_code == 201, response.text
        tags[name] = response.json()

    for child, parent in (
        ("homelab", "project"),
        ("server", "homelab"),
        ("shopping", "homelab"),
    ):
        response = client.post(
            f"/api/tags/{tags[child]['id']}/parents",
            json={"parent_tag_id": tags[parent]["id"]},
        )
        assert response.status_code == 201, response.text

    server = make_task(
        client,
        statuses,
        "Server research",
        status_id=statuses[1]["id"],
        tag_ids=[tags["server"]["id"], tags["research"]["id"]],
    )
    homelab = make_task(
        client,
        statuses,
        "Homelab notes",
        tag_ids=[tags["homelab"]["id"]],
    )
    shopping = make_task(
        client,
        statuses,
        "Buy rack parts",
        tag_ids=[tags["shopping"]["id"]],
    )
    personal = make_task(
        client,
        statuses,
        "Personal task",
        tag_ids=[tags["personal"]["id"]],
    )
    research = make_task(
        client,
        statuses,
        "Research only",
        tag_ids=[tags["research"]["id"]],
    )
    assert (
        client.post(
            f"/api/tasks/{server['id']}/block",
            json={"reason": "Waiting for hardware"},
        ).status_code
        == 201
    )

    include_all = client.get(
        "/api/tasks",
        params=[
            ("include_tag_id", tags["homelab"]["id"]),
            ("include_tag_id", tags["research"]["id"]),
            ("tag_match", "all"),
        ],
    ).json()
    assert [task["id"] for task in include_all] == [server["id"]]

    include_any = client.get(
        "/api/tasks",
        params=[
            ("include_tag_id", tags["homelab"]["id"]),
            ("include_tag_id", tags["personal"]["id"]),
            ("tag_match", "any"),
        ],
    ).json()
    assert {task["id"] for task in include_any} == {
        server["id"],
        homelab["id"],
        shopping["id"],
        personal["id"],
    }

    excluded = client.get(
        "/api/tasks",
        params=[
            ("include_tag_id", tags["project"]["id"]),
            ("exclude_tag_id", tags["shopping"]["id"]),
        ],
    ).json()
    assert {task["id"] for task in excluded} == {server["id"], homelab["id"]}

    combined = client.get(
        "/api/tasks",
        params=[
            ("finished", "false"),
            ("status_id", statuses[1]["id"]),
            ("blocked", "true"),
            ("search", "server"),
            ("include_tag_id", tags["project"]["id"]),
            ("include_tag_id", tags["research"]["id"]),
            ("tag_match", "all"),
            ("exclude_tag_id", tags["shopping"]["id"]),
        ],
    ).json()
    assert [task["id"] for task in combined] == [server["id"]]

    legacy = client.get(
        "/api/tasks",
        params={"tag_id": tags["project"]["id"]},
    ).json()
    assert {task["id"] for task in legacy} == {server["id"], homelab["id"], shopping["id"]}

    assert research["id"] not in {task["id"] for task in include_any}


def test_finish_and_reopen_are_independent_from_status(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    statuses = statuses_for(client)
    task = make_task(client, statuses)

    finished = client.post(f"/api/tasks/{task['id']}/finish").json()
    assert finished["finished_at"] is not None
    assert finished["status"]["id"] == task["status"]["id"]
    queue = client.get("/api/tasks", params={}).json()
    assert queue == []

    reopened = client.post(f"/api/tasks/{task['id']}/reopen").json()
    assert reopened["finished_at"] is None
    assert reopened["status"]["id"] == task["status"]["id"]


def test_multiple_active_blocks_and_repeated_history(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    statuses = statuses_for(client)
    task = make_task(client, statuses)

    blocked = client.post(f"/api/tasks/{task['id']}/block", json={"reason": "Waiting on hardware"})
    assert blocked.status_code == 201
    assert blocked.json()["current_block"]["reason"] == "Waiting on hardware"
    duplicate = client.post(f"/api/tasks/{task['id']}/block", json={"reason": "Another reason"})
    assert duplicate.status_code == 201
    assert len(duplicate.json()["active_blocks"]) == 2

    assert client.post(f"/api/tasks/{task['id']}/unblock").status_code == 409
    first_id = blocked.json()["current_block"]["id"]
    second_id = duplicate.json()["current_block"]["id"]
    assert client.post(f"/api/tasks/{task['id']}/blocks/{first_id}/unblock").status_code == 200
    assert client.post(f"/api/tasks/{task['id']}/blocks/{second_id}/unblock").status_code == 200
    again = client.post(f"/api/tasks/{task['id']}/block", json={"reason": "Waiting again"})
    assert again.status_code == 201
    assert len(again.json()["blocking_history"]) == 3
    assert len(again.json()["active_blocks"]) == 1


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
    statuses = statuses_for(client)
    task_data = make_task(client, statuses, priority=3)
    with SessionLocal() as db:
        task = db.get(Task, task_data["id"])
        assert task is not None
        task.created_at = datetime.now(UTC) - timedelta(days=10)
        task.last_worked_at = datetime.now(UTC) - timedelta(days=4)
        task.due_date = date.today() - timedelta(days=2)
        db.commit()
        assert score_task(task, datetime.now(UTC)) == pytest.approx(171.5, abs=0.1)

    invalid = client.put(
        "/api/settings/scoring",
        json={"scoring_formula": "open('/etc/passwd').read()"},
    )
    assert invalid.status_code == 422


def test_tag_creation_can_atomically_assign_parent(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    statuses_for(client)

    parent = client.post(
        "/api/tags",
        json={"name": "homelab"},
    ).json()
    created = client.post(
        "/api/tags",
        json={
            "name": "server maintenance",
            "color": "#587b6a",
            "parent_tag_id": parent["id"],
        },
    )
    assert created.status_code == 201, created.text
    assert [item["id"] for item in created.json()["parents"]] == [parent["id"]]

    invalid = client.post(
        "/api/tags",
        json={"name": "orphan", "parent_tag_id": 999999},
    )
    assert invalid.status_code == 404
    names = {tag["name"] for tag in client.get("/api/tags").json()}
    assert "orphan" not in names


def test_tag_names_keep_casing_and_reject_case_insensitive_duplicates(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    statuses_for(client)
    url = "/api/tags"

    created = client.post(url, json={"name": "  homeLab  "})
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "homeLab"
    assert client.post(url, json={"name": "HOMELAB"}).status_code == 409

    lower = client.post(url, json={"name": "server maintenance"})
    assert lower.status_code == 201, lower.text
    assert lower.json()["name"] == "server maintenance"
    updated = client.patch(f"{url}/{lower.json()['id']}", json={"name": "next-task"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "next-task"
    assert client.patch(f"{url}/{lower.json()['id']}", json={"name": "HOMELAB"}).status_code == 409


def test_tag_merge_moves_assignments_and_relationships_without_duplicates(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    statuses = statuses_for(client)

    tags: dict[str, dict] = {}
    for name in ("parent-a", "parent-b", "source", "destination", "child-a", "child-b"):
        response = client.post(
            "/api/tags",
            json={"name": name},
        )
        assert response.status_code == 201, response.text
        tags[name] = response.json()

    def add_parent(child: str, parent: str) -> None:
        response = client.post(
            f"/api/tags/{tags[child]['id']}/parents",
            json={"parent_tag_id": tags[parent]["id"]},
        )
        assert response.status_code == 201, response.text

    add_parent("source", "parent-a")
    add_parent("source", "parent-b")
    add_parent("destination", "parent-b")
    add_parent("child-a", "source")
    add_parent("child-b", "source")
    add_parent("child-b", "destination")

    source_only = make_task(
        client,
        statuses,
        "Source only",
        tag_ids=[tags["source"]["id"]],
    )
    both = make_task(
        client,
        statuses,
        "Already both",
        tag_ids=[tags["source"]["id"], tags["destination"]["id"]],
    )
    destination_only = make_task(
        client,
        statuses,
        "Destination only",
        tag_ids=[tags["destination"]["id"]],
    )

    preview = client.get(
        f"/api/tags/{tags['source']['id']}/merge-preview",
        params={"destination_tag_id": tags["destination"]["id"]},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json() == {
        "source_tag_id": tags["source"]["id"],
        "destination_tag_id": tags["destination"]["id"],
        "task_assignments": 2,
        "parent_relationships": 2,
        "child_relationships": 2,
    }

    merged = client.post(
        f"/api/tags/{tags['source']['id']}/merge",
        json={"destination_tag_id": tags["destination"]["id"]},
    )
    assert merged.status_code == 200, merged.text
    destination = merged.json()
    assert {item["name"] for item in destination["parents"]} == {"parent-a", "parent-b"}
    assert {item["name"] for item in destination["children"]} == {"child-a", "child-b"}
    assert destination["direct_task_count"] == 3

    remaining_names = {tag["name"] for tag in client.get("/api/tags").json()}
    assert "source" not in remaining_names

    for task_id in (source_only["id"], both["id"], destination_only["id"]):
        direct_names = [
            tag["name"] for tag in client.get(f"/api/tasks/{task_id}").json()["direct_tags"]
        ]
        assert direct_names.count("destination") == 1
        assert "source" not in direct_names


def test_tag_merge_cycle_failure_is_atomic(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("owner@example.com")
    statuses = statuses_for(client)

    tags: dict[str, dict] = {}
    for name in ("destination", "middle", "source"):
        tags[name] = client.post(
            "/api/tags",
            json={"name": name},
        ).json()

    assert (
        client.post(
            f"/api/tags/{tags['source']['id']}/parents",
            json={"parent_tag_id": tags["middle"]["id"]},
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/tags/{tags['middle']['id']}/parents",
            json={"parent_tag_id": tags["destination"]["id"]},
        ).status_code
        == 201
    )

    task = make_task(
        client,
        statuses,
        "Keep source",
        tag_ids=[tags["source"]["id"]],
    )

    preview = client.get(
        f"/api/tags/{tags['source']['id']}/merge-preview",
        params={"destination_tag_id": tags["destination"]["id"]},
    )
    assert preview.status_code == 422
    assert preview.json()["detail"] == "Merge would create a tag hierarchy cycle"

    merged = client.post(
        f"/api/tags/{tags['source']['id']}/merge",
        json={"destination_tag_id": tags["destination"]["id"]},
    )
    assert merged.status_code == 422

    tag_by_name = {tag["name"]: tag for tag in client.get("/api/tags").json()}
    assert "source" in tag_by_name
    assert [item["name"] for item in tag_by_name["source"]["parents"]] == ["middle"]
    assert [item["name"] for item in tag_by_name["middle"]["parents"]] == ["destination"]

    direct_names = [
        tag["name"] for tag in client.get(f"/api/tasks/{task['id']}").json()["direct_tags"]
    ]
    assert direct_names == ["source"]

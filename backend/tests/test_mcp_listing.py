from datetime import UTC, datetime

import pytest
from app.database import SessionLocal
from app.mcp_tasks import TaskListInput, list_tasks
from app.models import User
from app.routes.tasks import list_tasks_for_user
from app.services.scoring import plan_scoring
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select


@pytest.fixture
def fixed_scoring(monkeypatch):
    now = datetime.now(UTC)
    monkeypatch.setattr("app.routes.tasks.plan_scoring", lambda tasks: plan_scoring(tasks, now))


def test_shared_listing_matches_rest_filters(logged_in_client, fixed_scoring):
    client = logged_in_client("listing@example.com")
    first = client.post("/api/tasks", json={"title": "alpha", "priority": 1}).json()
    client.post("/api/tasks", json={"title": "beta", "priority": 2})

    for params in ({}, {"search": "alpha"}, {"finished": "true"}, {"actionable": "true"}):
        rest = client.get("/api/tasks", params=params)
        assert rest.status_code == 200
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == "listing@example.com"))
            shared = list_tasks_for_user(
                db,
                user,
                finished=params.get("finished") == "true",
                actionable=params.get("actionable") == "true",
                search=params.get("search"),
            )
            assert [task.model_dump(mode="json") for task in shared] == rest.json()
    assert first["id"] in [task["id"] for task in client.get("/api/tasks").json()]


def test_mcp_listing_paginates_after_ranking_and_matches_rest(logged_in_client, fixed_scoring):
    client = logged_in_client("mcp-list@example.com")
    tag = client.post("/api/tags", json={"name": "Work"}).json()
    client.post("/api/tasks", json={"title": "alpha", "priority": 1, "tag_ids": [tag["id"]]})
    client.post("/api/tasks", json={"title": "beta", "priority": 2, "tag_ids": [tag["id"]]})
    client.post("/api/tasks", json={"title": "other", "priority": 1})
    rest = client.get("/api/tasks", params={"include_tag_id": tag["id"]}).json()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "mcp-list@example.com"))
        first = list_tasks(db, user, TaskListInput(include_tag_ids=[tag["id"]], limit=1))
        second = list_tasks(db, user, TaskListInput(include_tag_ids=[tag["id"]], offset=1, limit=1))
    assert [first["items"][0]["id"], second["items"][0]["id"]] == [row["id"] for row in rest]
    assert first["next_offset"] == 1 and second["next_offset"] is None
    assert first["items"][0] == {key: rest[0][key] for key in first["items"][0]}
    assert "description" not in first["items"][0] and "user_id" not in first["items"][0]


def test_mcp_listing_rejects_foreign_and_missing_tags(logged_in_client):
    owner = logged_in_client("tag-owner@example.com")
    tag = owner.post("/api/tags", json={"name": "Private"}).json()
    logged_in_client("tag-visitor@example.com")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "tag-visitor@example.com"))
        details = []
        for tag_id in (tag["id"], tag["id"] + 10000):
            with pytest.raises(HTTPException) as error:
                list_tasks(db, user, TaskListInput(exclude_tag_ids=[tag_id]))
            details.append((error.value.status_code, str(error.value.detail)))
        assert details[0] == details[1]


def test_mcp_listing_only_returns_trusted_users_tasks(logged_in_client):
    first = logged_in_client("first@example.com")
    second = logged_in_client("second@example.com")
    first_id = first.post("/api/tasks", json={"title": "private first"}).json()["id"]
    second_id = second.post("/api/tasks", json={"title": "private second"}).json()["id"]
    with SessionLocal() as db:
        for email, expected_id in (
            ("first@example.com", first_id),
            ("second@example.com", second_id),
        ):
            user = db.scalar(select(User).where(User.email == email))
            result = list_tasks(db, user, TaskListInput())
            assert [item["id"] for item in result["items"]] == [expected_id]


@pytest.mark.parametrize(
    "values",
    [
        {"limit": 101},
        {"limit": 0},
        {"offset": -1},
        {"search": "a" * 301},
        {"include_tag_ids": [1] * 101},
        {"exclude_tag_ids": [0]},
    ],
)
def test_mcp_listing_rejects_unbounded_input(values):
    with pytest.raises(ValidationError):
        TaskListInput(**values)

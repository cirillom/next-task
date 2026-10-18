from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from app.database import SessionLocal
from app.models import User
from app.pomodoro_models import PomodoroSession
from fastapi.testclient import TestClient
from sqlalchemy import select


def test_pomodoro_settings_defaults_and_update(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("pomodoro@example.com")

    defaults = client.get("/api/pomodoro/settings")
    assert defaults.status_code == 200
    assert defaults.json() == {
        "focus_minutes": 25,
        "short_break_minutes": 5,
        "long_break_minutes": 15,
        "short_breaks_before_long": 3,
        "alert_mode": "notification",
    }

    updated = client.put(
        "/api/pomodoro/settings",
        json={
            "focus_minutes": 40,
            "short_break_minutes": 8,
            "long_break_minutes": 25,
            "short_breaks_before_long": 2,
            "alert_mode": "alarm",
        },
    )
    assert updated.status_code == 200
    assert updated.json() == {
        "focus_minutes": 40,
        "short_break_minutes": 8,
        "long_break_minutes": 25,
        "short_breaks_before_long": 2,
        "alert_mode": "alarm",
    }
    assert client.get("/api/pomodoro/settings").json() == updated.json()


def test_pomodoro_settings_are_per_user(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    first = logged_in_client("first-pomodoro@example.com")
    second = logged_in_client("second-pomodoro@example.com")

    response = first.put(
        "/api/pomodoro/settings",
        json={
            "focus_minutes": 50,
            "short_break_minutes": 10,
            "long_break_minutes": 30,
            "short_breaks_before_long": 4,
            "alert_mode": "notification",
        },
    )
    assert response.status_code == 200

    assert second.get("/api/pomodoro/settings").json()["focus_minutes"] == 25


def test_pomodoro_settings_validate_ranges(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("invalid-pomodoro@example.com")
    response = client.put(
        "/api/pomodoro/settings",
        json={
            "focus_minutes": 0,
            "short_break_minutes": 5,
            "long_break_minutes": 15,
            "short_breaks_before_long": 3,
            "alert_mode": "notification",
        },
    )
    assert response.status_code == 422


def test_pomodoro_session_is_one_synced_row_per_user(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    first = logged_in_client("synced-pomodoro@example.com")
    second = TestClient(first.app)
    assert (
        second.post(
            "/api/auth/login",
            json={"email": "synced-pomodoro@example.com", "password": "correct horse"},
        ).status_code
        == 200
    )
    task = first.post(
        "/api/tasks",
        json={
            "title": "Shared task",
        },
    ).json()

    created = first.post(
        "/api/pomodoro/session",
        json={"task_id": task["id"]},
    )
    assert created.status_code == 201
    assert created.json()["state"] == "ready"
    assert created.json()["phase"] == "focus"

    duplicate = second.post("/api/pomodoro/session", json={})
    assert duplicate.status_code == 200
    assert duplicate.json()["task_id"] == task["id"]

    started = first.post("/api/pomodoro/session/start")
    assert started.status_code == 200
    assert started.json()["state"] == "running"
    observed = second.get("/api/pomodoro/session").json()
    assert observed["ends_at"] == started.json()["ends_at"]
    assert observed["task_id"] == task["id"]

    with SessionLocal() as db:
        user_id = db.scalar(select(User.id).where(User.email == "synced-pomodoro@example.com"))
        assert user_id is not None
        rows = db.scalars(select(PomodoroSession).where(PomodoroSession.user_id == user_id)).all()
        assert len(rows) == 1


def test_pomodoro_session_keeps_combined_tag_scope(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("combined-pomodoro@example.com")
    other = logged_in_client("other-pomodoro@example.com")
    included = client.post("/api/tags", json={"name": "Today"}).json()
    excluded = client.post("/api/tags", json={"name": "Later"}).json()
    task = client.post("/api/tasks", json={"title": "Task", "tag_ids": [included["id"]]}).json()
    other_task = other.post("/api/tasks", json={"title": "Other task"}).json()
    scope = {
        "include_tag_ids": [included["id"]],
        "exclude_tag_ids": [excluded["id"]],
        "tag_match": "all",
    }
    created = client.post("/api/pomodoro/session", json={"scope": scope})
    assert created.status_code == 201, created.text
    assert created.json()["scope"] == scope
    assert (
        client.put("/api/pomodoro/session/task", json={"task_id": other_task["id"]}).status_code
        == 422
    )
    updated = client.put("/api/pomodoro/session/task", json={"task_id": task["id"]})
    assert updated.status_code == 200, updated.text
    assert updated.json()["task_id"] == task["id"]
    assert client.get("/api/pomodoro/session").json()["scope"] == scope


@pytest.mark.parametrize("state", ["ready", "running", "ringing"])
def test_session_scope_update_preserves_timer_and_pinned_task(
    logged_in_client: Callable[[str], TestClient], state: str
) -> None:
    client = logged_in_client(f"scope-{state}@example.com")
    second = TestClient(client.app)
    assert second.post(
        "/api/auth/login",
        json={"email": f"scope-{state}@example.com", "password": "correct horse"},
    ).status_code == 200
    old_tag = client.post("/api/tags", json={"name": "Old"}).json()
    new_tag = client.post("/api/tags", json={"name": "New"}).json()
    pinned = client.post(
        "/api/tasks", json={"title": "Keep pinned", "tag_ids": [old_tag["id"]]}
    ).json()
    old_scope = {
        "include_tag_ids": [old_tag["id"]],
        "exclude_tag_ids": [],
        "tag_match": "all",
    }
    created = client.post(
        "/api/pomodoro/session", json={"task_id": pinned["id"], "scope": old_scope}
    )
    assert created.status_code == 201
    if state == "running":
        assert client.post("/api/pomodoro/session/start").status_code == 200
    elif state == "ringing":
        with SessionLocal() as db:
            session = db.scalar(select(PomodoroSession))
            assert session is not None
            session.state = "ringing"
            db.commit()
    before = client.get("/api/pomodoro/session").json()
    new_scope = {
        "include_tag_ids": [new_tag["id"]],
        "exclude_tag_ids": [old_tag["id"]],
        "tag_match": "any",
    }
    changed = client.put(
        "/api/pomodoro/session/scope",
        json={"scope": new_scope, "expected_scope": old_scope},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["scope"] == new_scope
    for field in ("task_id", "tag_id", "phase", "state", "ends_at", "short_breaks_taken"):
        assert changed.json()[field] == before[field]
    assert second.get("/api/pomodoro/session").json()["scope"] == new_scope
    matching = second.get(
        "/api/tasks", params=[("include_tag_id", new_tag["id"])]
    ).json()
    assert pinned["id"] not in [task["id"] for task in matching]


def test_session_scope_update_rejects_invalid_tags_and_stale_edit(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("scope-owner@example.com")
    other = logged_in_client("scope-other@example.com")
    owned = client.post("/api/tags", json={"name": "Owned"}).json()
    foreign = other.post("/api/tags", json={"name": "Foreign"}).json()
    initial = {"include_tag_ids": [], "exclude_tag_ids": [], "tag_match": "all"}
    assert client.post("/api/pomodoro/session", json={"scope": initial}).status_code == 201

    for scope in (
        {"include_tag_ids": [foreign["id"]], "exclude_tag_ids": [], "tag_match": "all"},
        {"include_tag_ids": [999999], "exclude_tag_ids": [], "tag_match": "all"},
        {"include_tag_ids": [owned["id"]], "exclude_tag_ids": [owned["id"]], "tag_match": "all"},
        {"include_tag_ids": [], "exclude_tag_ids": [], "tag_match": "neither"},
    ):
        denied = client.put(
            "/api/pomodoro/session/scope", json={"scope": scope, "expected_scope": initial}
        )
        assert denied.status_code == 422
        assert client.get("/api/pomodoro/session").json()["scope"] == initial

    updated = {"include_tag_ids": [owned["id"]], "exclude_tag_ids": [], "tag_match": "all"}
    assert client.put(
        "/api/pomodoro/session/scope", json={"scope": updated, "expected_scope": initial}
    ).status_code == 200
    stale = client.put(
        "/api/pomodoro/session/scope", json={"scope": initial, "expected_scope": initial}
    )
    assert stale.status_code == 409
    assert client.get("/api/pomodoro/session").json()["scope"] == updated


def test_notification_advances_but_alarm_waits_for_dismissal(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("pomodoro-alerts@example.com")
    assert client.post("/api/pomodoro/session", json={}).status_code == 201
    assert client.post("/api/pomodoro/session/start").json()["state"] == "running"

    with SessionLocal() as db:
        session = db.scalar(select(PomodoroSession))
        assert session is not None
        session.ends_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    notification = client.get("/api/pomodoro/session").json()
    assert notification["state"] == "ready"
    assert notification["phase"] == "short-break"
    assert notification["short_breaks_taken"] == 1

    settings = client.get("/api/pomodoro/settings").json()
    settings["alert_mode"] = "alarm"
    assert client.put("/api/pomodoro/settings", json=settings).status_code == 200
    assert client.post("/api/pomodoro/session/start").json()["state"] == "running"

    with SessionLocal() as db:
        session = db.scalar(select(PomodoroSession))
        assert session is not None
        session.ends_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    ringing = client.get("/api/pomodoro/session").json()
    assert ringing["state"] == "ringing"
    assert ringing["phase"] == "short-break"
    assert client.post("/api/pomodoro/session/skip").status_code == 409

    dismissed = client.post("/api/pomodoro/session/dismiss").json()
    assert dismissed["state"] == "ready"
    assert dismissed["phase"] == "focus"

    assert client.delete("/api/pomodoro/session").status_code == 204
    assert client.get("/api/pomodoro/session").json() is None

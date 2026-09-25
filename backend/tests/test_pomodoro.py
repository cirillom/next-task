from collections.abc import Callable
from datetime import UTC, datetime, timedelta

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
    assert second.post(
        "/api/auth/login",
        json={"email": "synced-pomodoro@example.com", "password": "correct horse"},
    ).status_code == 200
    workspace = first.post("/api/workspaces", json={"name": "Focus"}).json()
    statuses = first.get(f"/api/workspaces/{workspace['id']}/statuses").json()
    task = first.post(
        "/api/tasks",
        json={
            "workspace_id": workspace["id"],
            "title": "Shared task",
            "status_id": statuses[0]["id"],
        },
    ).json()

    created = first.post(
        "/api/pomodoro/session",
        json={"workspace_id": workspace["id"], "task_id": task["id"]},
    )
    assert created.status_code == 201
    assert created.json()["state"] == "ready"
    assert created.json()["phase"] == "focus"

    duplicate = second.post(
        "/api/pomodoro/session", json={"workspace_id": workspace["id"]}
    )
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


def test_notification_advances_but_alarm_waits_for_dismissal(
    logged_in_client: Callable[[str], TestClient],
) -> None:
    client = logged_in_client("pomodoro-alerts@example.com")
    workspace = client.post("/api/workspaces", json={"name": "Alerts"}).json()
    assert client.post(
        "/api/pomodoro/session", json={"workspace_id": workspace["id"]}
    ).status_code == 201
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

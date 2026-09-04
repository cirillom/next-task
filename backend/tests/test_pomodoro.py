from collections.abc import Callable

from fastapi.testclient import TestClient


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
    }

    updated = client.put(
        "/api/pomodoro/settings",
        json={
            "focus_minutes": 40,
            "short_break_minutes": 8,
            "long_break_minutes": 25,
            "short_breaks_before_long": 2,
        },
    )
    assert updated.status_code == 200
    assert updated.json() == {
        "focus_minutes": 40,
        "short_break_minutes": 8,
        "long_break_minutes": 25,
        "short_breaks_before_long": 2,
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
        },
    )
    assert response.status_code == 422

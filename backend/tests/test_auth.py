from collections.abc import Callable

from app.database import SessionLocal
from app.main import app
from app.models import User
from fastapi.testclient import TestClient
from sqlalchemy import select


def test_password_is_hashed_and_login_sets_http_only_cookie(
    client: TestClient, create_user: Callable[[str, str, str], User]
) -> None:
    created = create_user("person@example.com")
    assert created.password_hash.startswith("$argon2id$")
    assert "correct horse" not in created.password_hash

    denied = client.post(
        "/api/auth/login", json={"email": "Person@Example.com", "password": "wrong password"}
    )
    assert denied.status_code == 401

    response = client.post(
        "/api/auth/login",
        json={"email": "person@example.com", "password": "correct horse"},
    )
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.json()["email"] == "person@example.com"
    assert client.get("/api/auth/me").status_code == 200


def test_signup_accepts_username_and_logs_user_in(client: TestClient) -> None:
    response = client.post(
        "/api/auth/signup",
        json={"identifier": "  NewUser  ", "password": "a secure password"},
    )
    assert response.status_code == 201
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.json()["email"] == "newuser"
    assert response.json()["display_name"] == "newuser"
    assert client.get("/api/auth/me").status_code == 200

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "newuser"))
        assert user is not None
        assert user.password_hash.startswith("$argon2id$")
        assert "a secure password" not in user.password_hash

    client.post("/api/auth/logout")
    login = client.post(
        "/api/auth/login",
        json={"email": "NEWUSER", "password": "a secure password"},
    )
    assert login.status_code == 200


def test_signup_accepts_email_and_rejects_duplicates_and_short_passwords(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/auth/signup",
        json={"identifier": "Person@Example.com", "password": "a secure password"},
    )
    assert created.status_code == 201
    assert created.json()["email"] == "person@example.com"
    assert created.json()["display_name"] == "person"

    duplicate = client.post(
        "/api/auth/signup",
        json={"identifier": "person@example.com", "password": "another secure password"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "That username or email is already in use"

    short = client.post(
        "/api/auth/signup",
        json={"identifier": "another-user", "password": "short"},
    )
    assert short.status_code == 422


def test_password_change_revokes_other_sessions(
    create_user: Callable[[str, str, str], User],
) -> None:
    create_user("person@example.com")
    first = TestClient(app)
    second = TestClient(app)
    for test_client in (first, second):
        assert (
            test_client.post(
                "/api/auth/login",
                json={"email": "person@example.com", "password": "correct horse"},
            ).status_code
            == 200
        )

    changed = first.post(
        "/api/auth/change-password",
        json={"current_password": "correct horse", "new_password": "a new secure password"},
    )
    assert changed.status_code == 200
    assert first.get("/api/auth/me").status_code == 200
    assert second.get("/api/auth/me").status_code == 401

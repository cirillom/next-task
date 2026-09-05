from collections.abc import Callable

from app.database import SessionLocal
from app.main import app
from app.models import Tag, Task, TaskStatus, User, Workspace, WorkspaceMember
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


def test_workspace_access_is_isolated_and_viewer_is_read_only(
    logged_in_client: Callable[[str], TestClient],
    create_user: Callable[[str, str, str], User],
) -> None:
    owner_client = logged_in_client("owner@example.com")
    other_client = logged_in_client("other@example.com")
    viewer = create_user("viewer@example.com")

    workspace = owner_client.post("/api/workspaces", json={"name": "Private"}).json()
    other_workspace = other_client.post("/api/workspaces", json={"name": "Other"}).json()
    assert owner_client.get(f"/api/workspaces/{other_workspace['id']}").status_code == 404

    added = owner_client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"email": viewer.email, "role": "viewer"},
    )
    assert added.status_code == 201

    viewer_client = TestClient(app)
    viewer_client.post("/api/auth/login", json={"email": viewer.email, "password": "correct horse"})
    assert viewer_client.get(f"/api/workspaces/{workspace['id']}/statuses").status_code == 200
    denied = viewer_client.post(
        f"/api/workspaces/{workspace['id']}/statuses",
        json={"name": "review", "score_value": 2},
    )
    assert denied.status_code == 403

    with SessionLocal() as db:
        assert db.get(User, viewer.id) is not None


def test_last_owner_cannot_be_demoted(logged_in_client: Callable[[str], TestClient]) -> None:
    owner_client = logged_in_client("owner@example.com")
    workspace = owner_client.post("/api/workspaces", json={"name": "Only owner"}).json()
    me = owner_client.get("/api/auth/me").json()

    response = owner_client.patch(
        f"/api/workspaces/{workspace['id']}/members/{me['id']}",
        json={"role": "editor"},
    )
    assert response.status_code == 409


def test_only_owner_can_delete_workspace_and_related_data_is_removed(
    logged_in_client: Callable[[str], TestClient],
    create_user: Callable[[str, str, str], User],
) -> None:
    owner_client = logged_in_client("owner@example.com")
    editor = create_user("editor@example.com")
    workspace = owner_client.post("/api/workspaces", json={"name": "Disposable"}).json()
    workspace_id = workspace["id"]

    assert (
        owner_client.post(
            f"/api/workspaces/{workspace_id}/members",
            json={"email": editor.email, "role": "editor"},
        ).status_code
        == 201
    )
    statuses = owner_client.get(f"/api/workspaces/{workspace_id}/statuses").json()
    tag = owner_client.post(
        f"/api/workspaces/{workspace_id}/tags", json={"name": "temporary"}
    ).json()
    task = owner_client.post(
        "/api/tasks",
        json={
            "workspace_id": workspace_id,
            "title": "Temporary task",
            "status_id": statuses[0]["id"],
            "assignee_ids": [editor.id],
            "tag_ids": [tag["id"]],
        },
    )
    assert task.status_code == 201

    editor_client = TestClient(app)
    assert (
        editor_client.post(
            "/api/auth/login",
            json={"email": editor.email, "password": "correct horse"},
        ).status_code
        == 200
    )
    denied = editor_client.delete(f"/api/workspaces/{workspace_id}")
    assert denied.status_code == 403
    assert owner_client.get(f"/api/workspaces/{workspace_id}").status_code == 200

    deleted = owner_client.delete(f"/api/workspaces/{workspace_id}")
    assert deleted.status_code == 204
    assert owner_client.get(f"/api/workspaces/{workspace_id}").status_code == 404
    assert editor_client.get(f"/api/workspaces/{workspace_id}").status_code == 404

    with SessionLocal() as db:
        assert db.get(Workspace, workspace_id) is None
        assert db.scalar(select(WorkspaceMember.workspace_id).where(WorkspaceMember.workspace_id == workspace_id)) is None
        assert db.scalar(select(TaskStatus.id).where(TaskStatus.workspace_id == workspace_id)) is None
        assert db.scalar(select(Task.id).where(Task.workspace_id == workspace_id)) is None
        assert db.scalar(select(Tag.id).where(Tag.workspace_id == workspace_id)) is None
        assert db.get(User, editor.id) is not None

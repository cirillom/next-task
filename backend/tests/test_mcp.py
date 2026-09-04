import base64
import hashlib
from urllib.parse import parse_qs, urlparse

from app.database import SessionLocal
from app.main import app as main_app
from app.mcp_app import create_app
from app.models import Tag, Task, TaskStatus, Workspace, WorkspaceMember, WorkspaceRole
from fastapi.testclient import TestClient
from sqlalchemy import select

MCP_BASE_URL = "http://localhost:8001"
MCP_RESOURCE = f"{MCP_BASE_URL}/mcp"
CHATGPT_REDIRECT = "https://chatgpt.com/connector_platform_oauth_redirect"
PROTOCOL_VERSION = "2025-06-18"


def _create_workspace(user_id: int) -> int:
    with SessionLocal() as db:
        workspace = Workspace(name="Home")
        db.add(workspace)
        db.flush()
        db.add_all(
            [
                WorkspaceMember(
                    user_id=user_id,
                    workspace_id=workspace.id,
                    role=WorkspaceRole.OWNER,
                ),
                TaskStatus(workspace_id=workspace.id, name="todo", score_value=0),
                TaskStatus(workspace_id=workspace.id, name="doing", score_value=1),
                Tag(workspace_id=workspace.id, name="chores"),
            ]
        )
        db.commit()
        return workspace.id


def _connect(client: TestClient, email: str, password: str) -> str:
    verifier = "v" * 64
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    registration = client.post(
        "/register",
        json={
            "redirect_uris": [CHATGPT_REDIRECT],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "client_name": "ChatGPT",
            "scope": "tasks",
            "application_type": "web",
        },
    )
    assert registration.status_code == 201
    client_id = registration.json()["client_id"]
    authorization = client.get(
        "/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": CHATGPT_REDIRECT,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "test-state",
            "scope": "tasks",
            "resource": MCP_RESOURCE,
        },
        follow_redirects=False,
    )
    assert authorization.status_code == 302
    request_token = parse_qs(urlparse(authorization.headers["location"]).query)["request"][0]
    login = client.post(
        "/login",
        data={
            "request": request_token,
            "email": email,
            "password": password,
            "decision": "approve",
        },
        follow_redirects=False,
    )
    assert login.status_code == 302
    callback = parse_qs(urlparse(login.headers["location"]).query)
    assert callback["state"] == ["test-state"]
    assert callback["iss"] == [MCP_BASE_URL]
    token = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": callback["code"][0],
            "redirect_uri": CHATGPT_REDIRECT,
            "code_verifier": verifier,
            "resource": MCP_RESOURCE,
        },
    )
    assert token.status_code == 200
    return token.json()["access_token"]


def _mcp_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
    }


def test_rejects_non_chatgpt_oauth_redirect() -> None:
    with TestClient(create_app(), base_url=MCP_BASE_URL) as client:
        response = client.post(
            "/register",
            json={
                "redirect_uris": ["https://attacker.example/callback"],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "scope": "tasks",
            },
        )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_redirect_uri"


def test_oauth_mcp_task_creation_and_account_revocation(create_user) -> None:
    user = create_user("owner@example.com")
    workspace_id = _create_workspace(user.id)

    with TestClient(create_app(), base_url=MCP_BASE_URL) as client:
        access_token = _connect(client, user.email, "correct horse")
        headers = _mcp_headers(access_token)
        initialize = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1"},
                },
            },
        )
        assert initialize.status_code == 200

        tools = client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert tools.status_code == 200
        assert "create_task" in {item["name"] for item in tools.json()["result"]["tools"]}

        created = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "create_task",
                    "arguments": {
                        "workspace_id": workspace_id,
                        "title": "Buy detergent",
                        "description": "Get the unscented kind.",
                        "status_name": "todo",
                        "priority": 3,
                        "tag_names": ["chores", "shopping"],
                    },
                },
            },
        )
        assert created.status_code == 200
        assert created.json()["result"]["isError"] is False

        with SessionLocal() as db:
            task = db.scalar(select(Task).where(Task.title == "Buy detergent"))
            assert task is not None
            assert task.priority == 3
            assert {tag.name for tag in task.tags} == {"chores", "shopping"}

        with TestClient(main_app) as account_client:
            login = account_client.post(
                "/api/auth/login",
                json={"email": user.email, "password": "correct horse"},
            )
            assert login.status_code == 200
            settings = account_client.get("/api/integrations/mcp")
            assert settings.json() == {
                "connector_url": MCP_RESOURCE,
                "active_connections": 1,
            }
            revoked = account_client.delete("/api/integrations/mcp")
            assert revoked.status_code == 200
            assert revoked.json()["active_connections"] == 0

        rejected = client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}},
        )
        assert rejected.status_code == 401
        assert "resource_metadata" in rejected.headers["www-authenticate"]

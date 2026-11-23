from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import anyio
import httpx2
import pytest
from app.auth.security import create_session, hash_token
from app.config import get_settings
from app.database import SessionLocal
from app.main import app, mcp_origin
from app.mcp_server import Verifier, create_server
from app.models import MCPCredential, MCPGrant, Task, User
from app.routes import mcp_oauth
from authlib.oauth2.rfc7636.challenge import create_s256_code_challenge
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from starlette.routing import Route

ORIGIN = "https://server.example"
CLIENT = "https://client.example/metadata"
CALLBACK = "https://client.example/callback"


@pytest.fixture
def workflow(monkeypatch, create_user):
    user = create_user("mcp-workflow@example.com")
    with SessionLocal() as db:
        cookie, _ = create_session(db, db.get(User, user.id))

    async def resolve(client_id):
        assert client_id == CLIENT
        return {
            "client_id": CLIENT,
            "client_name": "Test client",
            "redirect_uris": [CALLBACK],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
        }

    monkeypatch.setattr(mcp_oauth, "issuer", lambda: ORIGIN)
    monkeypatch.setattr(mcp_oauth.resolver, "resolve", resolve)
    server, mcp_app = create_server(ORIGIN)

    @asynccontextmanager
    async def lifespan(app):
        async with server.session_manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    app.include_router(mcp_oauth.router)
    app.router.routes.append(Route("/mcp", mcp_app))
    with TestClient(app, base_url=ORIGIN, follow_redirects=False) as client:
        client.cookies.set("next_task_session", cookie)
        yield client


def test_consent_exchange_tool_and_disconnect(workflow):
    client = workflow
    verifier = "a" * 43
    response = client.get(
        "/oauth/authorize",
        params={
            "client_id": CLIENT,
            "redirect_uri": CALLBACK,
            "response_type": "code",
            "scope": "tasks:read",
            "resource": ORIGIN + "/mcp",
            "code_challenge": create_s256_code_challenge(verifier),
            "code_challenge_method": "S256",
        },
    )
    assert response.status_code == 303
    request_id = parse_qs(urlsplit(response.headers["location"]).fragment.split("?", 1)[1])[
        "request"
    ][0]
    path = "/api/mcp/authorizations/" + request_id
    assert client.post(path, json={"allow": True}, headers={"Origin": ORIGIN}).status_code == 404
    assert client.get(path, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get(path).json()["account"] == "mcp-workflow@example.com"
    assert (
        client.post(
            path, json={"allow": True}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    response = client.post(path, json={"allow": True}, headers={"Origin": ORIGIN})
    assert response.status_code == 200
    callback = parse_qs(urlsplit(response.json()["redirect_uri"]).query)
    assert callback["iss"] == [ORIGIN]
    tokens = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT,
            "code": callback["code"][0],
            "redirect_uri": CALLBACK,
            "code_verifier": verifier,
            "resource": ORIGIN + "/mcp",
        },
    )
    assert tokens.status_code == 200
    access_token = tokens.json()["access_token"]
    first = anyio.run(Verifier().verify_token, access_token)
    second = anyio.run(Verifier().verify_token, access_token)
    assert first.subject == second.subject and first.subject is not None
    refreshed = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": CLIENT,
            "refresh_token": tokens.json()["refresh_token"],
            "resource": ORIGIN + "/mcp",
        },
    )
    assert refreshed.status_code == 200 and refreshed.json()["access_token"] != access_token
    headers = {
        "Authorization": "Bearer " + tokens.json()["access_token"],
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2026-07-28",
        "MCP-Method": "tools/call",
        "MCP-Name": "list_tasks",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "list_tasks",
            "arguments": {},
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientCapabilities": {},
            },
        },
    }
    result = client.post("/mcp", headers=headers, json=payload)
    assert result.status_code == 200, result.text
    assert "structuredContent" in result.json()["result"], result.text
    assert result.json()["result"]["structuredContent"]["items"] == []
    legacy_headers = {
        "Authorization": headers["Authorization"],
        "Accept": headers["Accept"],
        "MCP-Protocol-Version": "2025-11-25",
    }
    legacy = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "list_tasks", "arguments": {}},
    }
    legacy_result = client.post("/mcp", headers=legacy_headers, json=legacy)
    assert legacy_result.status_code == 200, legacy_result.text
    assert (
        legacy_result.json()["result"]["structuredContent"]
        == result.json()["result"]["structuredContent"]
    )
    assert (
        client.post("/mcp", headers={"Accept": headers["Accept"]}, json=payload).status_code == 401
    )
    assert (
        client.post(
            "/mcp", headers=headers | {"Origin": "https://evil.example"}, json=payload
        ).status_code
        == 403
    )
    assert (
        client.post("/mcp", headers=headers | {"Host": "evil.example"}, json=payload).status_code
        == 421
    )
    with SessionLocal() as db:
        credential = db.get(MCPCredential, hash_token(tokens.json()["access_token"]))
        credential.scope = "tags:read"
        db.commit()
    denied = client.post("/mcp", headers=headers, json=payload).json()["result"]
    assert denied["isError"] is True
    assert "insufficient_scope" in denied["_meta"]["mcp/www_authenticate"]
    connection = client.get("/api/settings/mcp").json()["connections"][0]
    assert (
        client.delete(
            "/api/settings/mcp/connections/" + str(connection["id"]), headers={"Origin": ORIGIN}
        ).status_code
        == 204
    )
    assert client.post("/mcp", headers=headers, json=payload).status_code == 401


def test_production_asgi_routing_and_repeated_lifespan(tmp_path, monkeypatch):
    if not mcp_origin:
        pytest.skip("Public application URL is not configured")
    (tmp_path / "index.html").write_text("SPA fixture", encoding="utf-8")
    monkeypatch.setattr(get_settings(), "frontend_dir", tmp_path)
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    for _ in range(2):
        with TestClient(app, base_url=mcp_origin, follow_redirects=False) as client:
            response = client.post(
                "/mcp", json=payload, headers={"Accept": "application/json, text/event-stream"}
            )
            assert response.status_code == 401
            assert "www-authenticate" in response.headers
            legacy = {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}}
            assert client.post("/mcp", json=legacy).status_code == 401
            assert client.get("/api/health").json() == {"status": "ok"}
            assert client.get("/some-page").text == "SPA fixture"
            auth_metadata = client.get(
                "/.well-known/oauth-authorization-server", headers={"Host": "evil.example"}
            )
            assert auth_metadata.json()["issuer"] == mcp_origin
            assert auth_metadata.json()["revocation_endpoint_auth_methods_supported"] == ["none"]
            metadata = client.get("/.well-known/oauth-protected-resource/mcp")
            assert (
                metadata.status_code == 200 and metadata.json()["resource"] == mcp_origin + "/mcp"
            )
            assert client.get("/.well-known/oauth-protected-resource").json() == metadata.json()
            assert client.post("/mcp/mcp", json=payload).status_code in (404, 405)
            assert client.post("/mcp?access_token=secret", json=payload).status_code == 400


def test_concurrent_code_redemption_is_single_use(workflow):
    client = workflow
    verifier = "b" * 43
    response = client.get(
        "/oauth/authorize",
        params={
            "client_id": CLIENT,
            "redirect_uri": CALLBACK,
            "response_type": "code",
            "scope": "tasks:read",
            "resource": ORIGIN + "/mcp",
            "code_challenge": create_s256_code_challenge(verifier),
            "code_challenge_method": "S256",
        },
    )
    request_id = parse_qs(urlsplit(response.headers["location"]).fragment.split("?", 1)[1])[
        "request"
    ][0]
    path = "/api/mcp/authorizations/" + request_id
    assert client.get(path).status_code == 200
    result = client.post(path, json={"allow": True}, headers={"Origin": ORIGIN})
    code = parse_qs(urlsplit(result.json()["redirect_uri"]).query)["code"][0]
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT,
        "code": code,
        "redirect_uri": CALLBACK,
        "code_verifier": verifier,
        "resource": ORIGIN + "/mcp",
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(
            executor.map(lambda _: client.post("/oauth/token", data=data).status_code, range(2))
        )
    assert sorted(statuses) == [200, 400]
    assert client.get("/api/settings/mcp").json()["connections"] == []


def test_authorization_is_bound_to_browser_session(workflow, create_user):
    client = workflow
    original_cookie = client.cookies.get("next_task_session")
    response = client.get(
        "/oauth/authorize",
        params={
            "client_id": CLIENT,
            "redirect_uri": CALLBACK,
            "response_type": "code",
            "resource": ORIGIN + "/mcp",
            "code_challenge": create_s256_code_challenge("c" * 43),
            "code_challenge_method": "S256",
        },
    )
    request_id = parse_qs(urlsplit(response.headers["location"]).fragment.split("?", 1)[1])[
        "request"
    ][0]
    path = "/api/mcp/authorizations/" + request_id
    assert client.get(path).status_code == 200
    other = create_user("other-mcp@example.com")
    with SessionLocal() as db:
        other_cookie, _ = create_session(db, db.get(User, other.id))
    client.cookies.set("next_task_session", other_cookie)
    assert client.get(path).status_code == 404
    assert client.post(path, json={"allow": True}, headers={"Origin": ORIGIN}).status_code == 404
    client.cookies.set("next_task_session", original_cookie)
    assert client.post(path, json={"allow": False}, headers={"Origin": ORIGIN}).status_code == 200


def test_oauth_rate_limit_precedes_client_metadata_fetch(workflow, monkeypatch):
    monkeypatch.setattr(mcp_oauth, "reserve_window_attempt", lambda *args, **kwargs: None)
    assert workflow.get("/oauth/authorize", params={"client_id": CLIENT}).status_code == 429


def test_oauth_rejects_oversized_duplicate_and_url_credentials(workflow):
    form = {"Content-Type": "application/x-www-form-urlencoded"}
    assert workflow.post("/oauth/token", content="a" * 8193, headers=form).status_code == 413
    assert (
        workflow.post("/oauth/token", content="client_id=a&client_id=b", headers=form).status_code
        == 400
    )
    assert workflow.post("/oauth/token", json={}).status_code == 415
    assert (
        workflow.post("/oauth/token?access_token=secret", content="", headers=form).status_code
        == 400
    )
    assert workflow.get("/oauth/authorize?access_token=secret").status_code == 400


def test_authorization_errors_preserve_state_and_issuer(workflow):
    response = workflow.get(
        "/oauth/authorize",
        params={
            "client_id": CLIENT,
            "redirect_uri": CALLBACK,
            "response_type": "code",
            "resource": ORIGIN + "/mcp",
            "code_challenge": "a" * 43,
            "code_challenge_method": "plain",
            "state": "expected-state",
        },
    )
    assert response.status_code == 302
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["error"] == ["invalid_request"]
    assert query["state"] == ["expected-state"] and query["iss"] == [ORIGIN]


def test_bad_verifier_does_not_consume_code_and_oauth_revoke_invalidates_it(workflow):
    client = workflow
    verifier = "d" * 43
    response = client.get(
        "/oauth/authorize",
        params={
            "client_id": CLIENT,
            "redirect_uri": CALLBACK,
            "response_type": "code",
            "resource": ORIGIN + "/mcp",
            "code_challenge": create_s256_code_challenge(verifier),
            "code_challenge_method": "S256",
        },
    )
    request_id = parse_qs(urlsplit(response.headers["location"]).fragment.split("?", 1)[1])[
        "request"
    ][0]
    path = "/api/mcp/authorizations/" + request_id
    assert client.get(path).status_code == 200
    result = client.post(path, json={"allow": True}, headers={"Origin": ORIGIN})
    code = parse_qs(urlsplit(result.json()["redirect_uri"]).query)["code"][0]
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT,
        "code": code,
        "redirect_uri": CALLBACK,
        "code_verifier": "e" * 43,
        "resource": ORIGIN + "/mcp",
    }
    assert client.post("/oauth/token", data=data).status_code == 400
    data["code_verifier"] = verifier
    token = client.post("/oauth/token", data=data).json()["access_token"]
    assert anyio.run(Verifier().verify_token, token) is not None
    response = client.post("/oauth/revoke", data={"client_id": CLIENT, "token": token})
    assert response.status_code == 200
    assert anyio.run(Verifier().verify_token, token) is None


def test_modern_and_legacy_sdk_clients_return_equivalent_results(create_user):
    user = create_user("sdk-mcp@example.com")
    other = create_user("sdk-other@example.com")
    sdk_origin = mcp_origin or ORIGIN
    with SessionLocal() as db:
        task_ids = []
        for person, token in ((user, "sdk-test-token"), (other, "sdk-other-token")):
            db.get(User, person.id).scoring_formula = "priority * 25"
            task = Task(user_id=person.id, title="Private task", priority=1)
            grant = MCPGrant(
                user_id=person.id,
                client_id=CLIENT,
                client_name="Test",
                redirect_uri=CALLBACK,
                resource=sdk_origin + "/mcp",
                scope="tasks:read",
            )
            db.add_all([task, grant])
            db.flush()
            task_ids.append(task.id)
            db.add(
                MCPCredential(
                    token_hash=hash_token(token),
                    grant_id=grant.id,
                    kind="access",
                    scope="tasks:read",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
        db.commit()

    async def run_clients():
        if mcp_origin:
            sdk_app = app
            lifespan = sdk_app.router.lifespan_context(sdk_app)
        else:
            server, mcp_app = create_server(sdk_origin)
            sdk_app = FastAPI()
            sdk_app.router.routes.append(Route("/mcp", mcp_app))
            lifespan = server.session_manager.run()
        results = []
        async with lifespan:
            for modern, token in (
                (True, "sdk-test-token"),
                (False, "sdk-test-token"),
                (True, "sdk-other-token"),
            ):
                async with (
                    httpx2.AsyncClient(
                        transport=httpx2.ASGITransport(app=sdk_app),
                        headers={"Authorization": "Bearer " + token},
                    ) as http,
                    streamable_http_client(sdk_origin + "/mcp", http_client=http) as streams,
                    ClientSession(*streams) as session,
                ):
                    if modern:
                        await session.discover()
                    else:
                        await session.initialize()
                    tools = await session.list_tools()
                    assert [tool.name for tool in tools.tools] == ["list_tasks"]
                    assert tools.tools[0].annotations.read_only_hint is True
                    assert tools.tools[0].annotations.open_world_hint is False
                    assert tools.tools[0].meta["securitySchemes"][0]["scopes"] == ["tasks:read"]
                    result = await session.call_tool("list_tasks", {})
                    results.append(result.structured_content)
                    if token == "sdk-test-token":
                        injected = await session.call_tool("list_tasks", {"user_id": other.id})
                        assert (
                            injected.is_error
                            or injected.structured_content == result.structured_content
                        )
        assert results[0] == results[1]
        assert [[item["id"] for item in result["items"]] for result in results] == [
            [task_ids[0]],
            [task_ids[0]],
            [task_ids[1]],
        ]

    anyio.run(run_clients)


def test_token_survives_production_lifespan_restart(create_user):
    if not mcp_origin:
        pytest.skip("Public application URL is not configured")
    user = create_user("restart-mcp@example.com")
    token = "restart-test-token"
    with SessionLocal() as db:
        grant = MCPGrant(
            user_id=user.id,
            client_id=CLIENT,
            client_name="Test",
            redirect_uri=CALLBACK,
            resource=mcp_origin + "/mcp",
            scope="tasks:read",
        )
        db.add(grant)
        db.flush()
        db.add(
            MCPCredential(
                token_hash=hash_token(token),
                grant_id=grant.id,
                kind="access",
                scope="tasks:read",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        db.commit()
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "list_tasks", "arguments": {}},
    }
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-11-25",
    }
    for _ in range(2):
        with TestClient(app, base_url=mcp_origin) as client:
            response = client.post("/mcp", headers=headers, json=payload)
            assert response.status_code == 200
            assert response.json()["result"]["structuredContent"]["items"] == []


def test_oauth_to_tool_through_production_asgi(monkeypatch, create_user):
    if not mcp_origin:
        pytest.skip("Public application URL is not configured")
    user = create_user("production-asgi-mcp@example.com")
    with SessionLocal() as db:
        cookie, _ = create_session(db, db.get(User, user.id))

    async def resolve(client_id):
        assert client_id == CLIENT
        return {
            "client_id": CLIENT,
            "client_name": "Test client",
            "redirect_uris": [CALLBACK],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
        }

    monkeypatch.setattr(mcp_oauth.resolver, "resolve", resolve)
    verifier = "f" * 43
    with TestClient(app, base_url=mcp_origin, follow_redirects=False) as client:
        client.cookies.set("next_task_session", cookie)
        response = client.get(
            "/oauth/authorize",
            params={
                "client_id": CLIENT,
                "redirect_uri": CALLBACK,
                "response_type": "code",
                "resource": mcp_origin + "/mcp",
                "code_challenge": create_s256_code_challenge(verifier),
                "code_challenge_method": "S256",
            },
        )
        assert response.status_code == 303
        request_id = parse_qs(urlsplit(response.headers["location"]).fragment.split("?", 1)[1])[
            "request"
        ][0]
        path = "/api/mcp/authorizations/" + request_id
        assert client.get(path).status_code == 200
        result = client.post(path, json={"allow": True}, headers={"Origin": mcp_origin})
        code = parse_qs(urlsplit(result.json()["redirect_uri"]).query)["code"][0]
        token = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": CLIENT,
                "code": code,
                "redirect_uri": CALLBACK,
                "code_verifier": verifier,
                "resource": mcp_origin + "/mcp",
            },
        )
        assert token.status_code == 200
        headers = {
            "Authorization": "Bearer " + token.json()["access_token"],
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-11-25",
        }
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "list_tasks", "arguments": {}},
        }
        result = client.post("/mcp", json=payload, headers=headers)
        assert (
            result.status_code == 200
            and result.json()["result"]["structuredContent"]["items"] == []
        )
        assert result.headers["cache-control"] == "no-store"

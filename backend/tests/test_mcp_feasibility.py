"""Isolated feasibility harness: no application routes or real user data."""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import anyio
import httpx
import pytest
from app.cimd import ClientMetadataResolver, InvalidClientMetadata
from app.oauth_bridge import OAuthRequest, oauth_request, oauth_response
from authlib.common.security import generate_token
from authlib.oauth2.rfc6749 import AuthorizationServer, InvalidRequestError, grants
from authlib.oauth2.rfc6750 import BearerTokenGenerator
from authlib.oauth2.rfc7636 import CodeChallenge
from authlib.oauth2.rfc7636.challenge import create_s256_code_challenge
from authlib.oauth2.rfc9207 import IssuerParameter
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from mcp.client.auth import OAuthFlowError
from mcp.client.auth.utils import validate_authorization_response_iss
from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.auth import OAuthMetadata
from starlette.responses import JSONResponse
from starlette.routing import Route

ISSUER = "https://server.example"
RESOURCE = ISSUER + "/mcp"
CLIENT = "https://client.example/metadata"
CALLBACK = "https://client.example/callback"
VERIFIER = "a" * 43


class Client:
    def __init__(self, metadata):
        self.metadata = metadata

    def get_client_id(self):
        return self.metadata["client_id"]

    def get_default_redirect_uri(self):
        return None

    def check_redirect_uri(self, uri):
        return uri in self.metadata["redirect_uris"]

    def check_endpoint_auth_method(self, method, endpoint):
        return method == "none"

    def check_response_type(self, response_type):
        return response_type in self.metadata.get("response_types", ["code"])

    def check_grant_type(self, grant_type):
        return grant_type in self.metadata.get("grant_types", ["authorization_code"])

    def get_allowed_scope(self, scope):
        return scope or "tasks:read"


@dataclass
class Credential:
    client_id: str
    redirect_uri: str
    scope: str
    resource: str
    code_challenge: str = ""
    code_challenge_method: str = ""
    value: str = ""

    def get_redirect_uri(self):
        return self.redirect_uri

    def get_scope(self):
        return self.scope

    def check_client(self, client):
        return self.client_id == client.get_client_id()


@pytest.fixture
def harness(monkeypatch):
    codes = {}
    refresh = {}
    access = {}
    clients = {}
    resolver = ClientMetadataResolver()
    httpx_client = httpx.AsyncClient

    async def dns(host, port, **kwargs):
        return [(2, 1, 6, "", ("8.8.8.8", port))]

    def metadata(request):
        return httpx.Response(
            200,
            json={
                "client_id": CLIENT,
                "client_name": "Fixture",
                "redirect_uris": [CALLBACK],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
            },
        )

    def metadata_client(**kwargs):
        return httpx_client(transport=httpx.MockTransport(metadata), **kwargs)

    monkeypatch.setattr(anyio, "getaddrinfo", dns)
    monkeypatch.setattr(httpx, "AsyncClient", metadata_client)

    class Server(AuthorizationServer):
        def query_client(self, client_id):
            return clients.get(client_id)

        def create_oauth2_request(self, request):
            assert isinstance(request, OAuthRequest)
            return request

        def handle_response(self, status, body, headers):
            return oauth_response(status, body, headers)

        def send_signal(self, name, *args, **kwargs):
            pass

        def save_token(self, token, request):
            credential = request.authorization_code or request.refresh_token
            access[token["access_token"]] = credential
            if "refresh_token" in token:
                refresh[token["refresh_token"]] = credential

    class CodeGrant(grants.AuthorizationCodeGrant):
        TOKEN_ENDPOINT_AUTH_METHODS = ["none"]

        def validate_authorization_request(self):
            redirect = super().validate_authorization_request()
            data = self.request.payload.data
            if (
                data.get("resource") != RESOURCE
                or not data.get("code_challenge")
                or data.get("code_challenge_method") != "S256"
            ):
                raise InvalidRequestError(redirect_uri=redirect)
            return redirect

        def save_authorization_code(self, code, request):
            data = request.payload.data
            codes[code] = Credential(
                CLIENT,
                data["redirect_uri"],
                request.scope,
                RESOURCE,
                data["code_challenge"],
                data["code_challenge_method"],
                code,
            )

        def query_authorization_code(self, code, client):
            credential = codes.get(code)
            if (
                credential
                and credential.check_client(client)
                and (self.request.form.get("resource") == credential.resource)
            ):
                return credential
            return None

        def delete_authorization_code(self, credential):
            codes.pop(credential.value)

        def authenticate_user(self, credential):
            return "fixture-user"

    class RefreshGrant(grants.RefreshTokenGrant):
        TOKEN_ENDPOINT_AUTH_METHODS = ["none"]
        INCLUDE_NEW_REFRESH_TOKEN = True

        def authenticate_refresh_token(self, token):
            credential = refresh.get(token)
            if credential and self.request.form.get("resource") == credential.resource:
                return credential
            return None

        def authenticate_user(self, credential):
            return "fixture-user"

        def revoke_old_credential(self, credential):
            refresh.pop(self.request.form["refresh_token"])

    class Issuer(IssuerParameter):
        def get_issuer(self):
            return ISSUER

    server = Server(scopes_supported=["tasks:read"])
    server.register_grant(CodeGrant, [CodeChallenge(required=True)])
    server.register_grant(RefreshGrant)
    server.register_extension(Issuer())
    server.register_token_generator(
        "default",
        BearerTokenGenerator(
            lambda **_: generate_token(48), lambda **_: generate_token(48), expires_generator=3600
        ),
    )

    class Verifier:
        async def verify_token(self, token):
            credential = access.get(token)
            if credential:
                return AccessToken(
                    token=token,
                    client_id=CLIENT,
                    scopes=["tasks:read"],
                    resource=credential.resource,
                    subject="fixture-user",
                )
            return None

    mcp = MCPServer(
        "feasibility",
        token_verifier=Verifier(),
        auth=AuthSettings(
            issuer_url=ISSUER, resource_server_url=RESOURCE, validate_token_resource=True
        ),
    )
    mcp_app = mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["server.example"],
            allowed_origins=[ISSUER],
        ),
    )

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(lifespan=lifespan)

    @app.get("/.well-known/oauth-authorization-server")
    async def issuer_metadata():
        return {
            "issuer": ISSUER,
            "authorization_endpoint": ISSUER + "/oauth/authorize",
            "token_endpoint": ISSUER + "/oauth/token",
            "client_id_metadata_document_supported": True,
            "authorization_response_iss_parameter_supported": True,
            "token_endpoint_auth_methods_supported": ["none"],
        }

    @app.get("/oauth/authorize")
    async def authorize(request: Request):
        oauth = await oauth_request(request, ISSUER)
        try:
            metadata = await resolver.resolve(oauth.payload.client_id)
        except InvalidClientMetadata:
            return JSONResponse({"error": "invalid_client"}, status_code=400)
        clients[metadata["client_id"]] = Client(metadata)
        user = None if request.query_params.get("deny") == "true" else "fixture-user"
        return server.create_authorization_response(oauth, grant_user=user)

    @app.post("/oauth/token")
    async def token(request: Request):
        oauth = await oauth_request(request, ISSUER)
        try:
            metadata = await resolver.resolve(oauth.payload.client_id)
        except InvalidClientMetadata:
            return JSONResponse({"error": "invalid_client"}, status_code=400)
        clients[metadata["client_id"]] = Client(metadata)
        return server.create_token_response(oauth)

    app.router.routes.append(Route("/mcp", mcp_app))
    with TestClient(app, base_url=ISSUER, follow_redirects=False) as http:
        yield http, access


def authorize(http, **overrides):
    params = {
        "client_id": CLIENT,
        "redirect_uri": CALLBACK,
        "response_type": "code",
        "scope": "tasks:read",
        "state": "state",
        "resource": RESOURCE,
        "code_challenge": create_s256_code_challenge(VERIFIER),
        "code_challenge_method": "S256",
    } | overrides
    return http.get("/oauth/authorize", params=params)


def exchange(http, code, **overrides):
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT,
        "code": code,
        "redirect_uri": CALLBACK,
        "code_verifier": VERIFIER,
        "resource": RESOURCE,
    } | overrides
    return http.post("/oauth/token", data=data)


def test_code_exchange_refresh_and_mcp_resource(harness):
    http, _ = harness
    response = authorize(http)
    assert response.status_code == 302
    params = parse_qs(urlsplit(response.headers["location"]).query)
    assert params["iss"] == [ISSUER] and params["state"] == ["state"]
    tokens = exchange(http, params["code"][0]).json()
    assert tokens["access_token"] and tokens["refresh_token"]
    assert exchange(http, params["code"][0]).status_code == 400
    refreshed = http.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": CLIENT,
            "refresh_token": tokens["refresh_token"],
            "resource": RESOURCE,
        },
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != tokens["refresh_token"]
    assert (
        http.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": CLIENT,
                "refresh_token": tokens["refresh_token"],
                "resource": RESOURCE,
            },
        ).status_code
        == 400
    )
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientCapabilities": {},
            }
        },
    }
    headers = {"Accept": "application/json, text/event-stream"}
    assert http.post("/mcp", json=payload, headers=headers).status_code == 401
    headers["Authorization"] = "Bearer " + tokens["access_token"]
    headers["MCP-Protocol-Version"] = "2026-07-28"
    headers["MCP-Method"] = "tools/list"
    result = http.post("/mcp", json=payload, headers=headers)
    assert result.status_code == 200, result.text


@pytest.mark.parametrize(
    "overrides",
    [
        {"resource": "https://other.example/mcp"},
        {"code_challenge_method": "plain"},
        {"code_challenge": ""},
    ],
)
def test_authorization_policy_errors_include_issuer(harness, overrides):
    response = authorize(harness[0], **overrides)
    params = parse_qs(urlsplit(response.headers["location"]).query)
    assert params["error"] == ["invalid_request"] and params["iss"] == [ISSUER]


@pytest.mark.parametrize(
    "overrides",
    [
        {"code_verifier": "b" * 43},
        {"redirect_uri": "https://evil.example/"},
        {"resource": "https://evil.example/mcp"},
        {"client_id": "https://evil.example/meta"},
        {"client_secret": "not-allowed"},
    ],
)
def test_exchange_rejects_mismatched_binding(harness, overrides):
    http = harness[0]
    code = parse_qs(urlsplit(authorize(http).headers["location"]).query)["code"][0]
    assert exchange(http, code, **overrides).status_code in (400, 401)


def test_sdk_rejects_wrong_token_resource(harness):
    http, access = harness
    access["wrong-resource"] = Credential(
        CLIENT, CALLBACK, "tasks:read", "https://other.example/mcp"
    )
    response = http.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer wrong-resource",
        },
    )
    assert response.status_code == 401


def test_sdk_client_checks_issuer():
    metadata = OAuthMetadata(
        issuer=ISSUER,
        authorization_endpoint=ISSUER + "/oauth/authorize",
        token_endpoint=ISSUER + "/oauth/token",
        authorization_response_iss_parameter_supported=True,
    )
    validate_authorization_response_iss(ISSUER, metadata)
    for issuer in (None, "https://other.example"):
        with pytest.raises(OAuthFlowError):
            validate_authorization_response_iss(issuer, metadata)


def test_metadata_and_denied_authorization_identify_issuer(harness):
    http = harness[0]
    metadata = http.get("/.well-known/oauth-authorization-server").json()
    assert metadata["issuer"] == ISSUER
    assert metadata["authorization_response_iss_parameter_supported"] is True
    response = authorize(http, deny="true")
    params = parse_qs(urlsplit(response.headers["location"]).query)
    assert params["error"] == ["access_denied"] and params["iss"] == [ISSUER]

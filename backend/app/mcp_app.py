from importlib.metadata import version
from urllib.parse import urlparse

from mcp.server.auth.settings import (
    AuthSettings,
    ClientRegistrationOptions,
    RevocationOptions,
)
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.config import get_settings
from app.mcp_oauth import SCOPES, NextTaskOAuthProvider, install_oauth_routes
from app.mcp_tools import install_tools


def create_app():
    settings = get_settings()
    provider = NextTaskOAuthProvider()
    public_url = settings.mcp_public_url.rstrip("/")
    parsed_public_url = urlparse(public_url)

    server = MCPServer(
        name="next-task",
        title="Next Task",
        description=(
            "Read and manage tasks in the authenticated user's self-hosted Next Task account."
        ),
        instructions=(
            "Use list_workspaces and get_workspace_context before creating tasks. Reuse existing "
            "statuses and tags where appropriate. Before any write, show the proposed task or "
            "change to the user and obtain explicit confirmation. Never invent workspace IDs, "
            "task IDs, assignees, or existing tag names."
        ),
        website_url="https://tasks.cirillo/",
        version=version("next-task"),
        auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=public_url,
            resource_server_url=f"{public_url}/mcp",
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=SCOPES,
                default_scopes=SCOPES,
            ),
            revocation_options=RevocationOptions(enabled=True),
            required_scopes=SCOPES,
        ),
    )

    install_tools(server)
    install_oauth_routes(server, provider)

    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        host="0.0.0.0",
        max_request_body_size=256 * 1024,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[
                parsed_public_url.netloc,
                "127.0.0.1:*",
                "localhost:*",
            ],
            allowed_origins=[public_url, "https://chatgpt.com"],
        ),
    )

    async def oauth_authorization_server_metadata(_request):
        return JSONResponse(
            {
                "issuer": public_url,
                "authorization_endpoint": f"{public_url}/authorize",
                "token_endpoint": f"{public_url}/token",
                "registration_endpoint": f"{public_url}/register",
                "scopes_supported": SCOPES,
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "token_endpoint_auth_methods_supported": [
                    "none",
                    "client_secret_post",
                    "client_secret_basic",
                ],
                "revocation_endpoint": f"{public_url}/revoke",
                "revocation_endpoint_auth_methods_supported": [
                    "none",
                    "client_secret_post",
                    "client_secret_basic",
                ],
                "code_challenge_methods_supported": ["S256"],
            },
            headers={
                "Cache-Control": "public, max-age=300",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
            },
        )

    app.routes.insert(
        0,
        Route(
            "/.well-known/oauth-authorization-server",
            endpoint=oauth_authorization_server_metadata,
            methods=["GET", "OPTIONS"],
        ),
    )
    return app


app = create_app()

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import urlsplit

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from app.auth.rate_limit import reserve_window_attempt
from app.auth.security import _as_utc, hash_token
from app.database import SessionLocal
from app.mcp_tasks import TaskListInput, TaskListOutput
from app.mcp_tasks import list_tasks as query_tasks
from app.models import MCPCredential, User


class Verifier:
    async def verify_token(self, token: str) -> AccessToken | None:
        with SessionLocal() as db:
            credential = db.get(MCPCredential, hash_token(token))
            if not credential or credential.kind != "access" or credential.consumed_at:
                return None
            grant = credential.grant
            if (
                grant.revoked_at
                or _as_utc(credential.expires_at) <= datetime.now(UTC)
                or not db.get(User, grant.user_id)
            ):
                return None
            return AccessToken(
                token=token,
                client_id=grant.client_id,
                scopes=credential.scope.split(),
                resource=grant.resource,
                subject=str(grant.user_id),
                expires_at=int(_as_utc(credential.expires_at).timestamp()),
            )


def create_server(origin: str):
    resource = origin + "/mcp"
    server = MCPServer(
        "Next Task",
        token_verifier=Verifier(),
        auth=AuthSettings(
            issuer_url=origin, resource_server_url=resource, validate_token_resource=True
        ),
    )

    @server.tool(
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
        meta={"securitySchemes": [{"type": "oauth2", "scopes": ["tasks:read"]}]},
        structured_output=True,
    )
    async def list_tasks(
        finished: bool | None = False,
        abandoned: Literal["exclude", "only", "include"] = "exclude",
        search: Annotated[str | None, Field(max_length=300)] = None,
        blocked: bool | None = None,
        actionable: bool = False,
        include_tag_ids: Annotated[
            list[int] | None,
            Field(
                max_length=100,
                description="Unique tag IDs, including descendants; omitted means all tags.",
            ),
        ] = None,
        exclude_tag_ids: Annotated[
            list[int] | None,
            Field(
                max_length=100,
                description=(
                    "Unique tag IDs to exclude, including descendants; exclusions take precedence."
                ),
            ),
        ] = None,
        tag_match: Literal["all", "any"] = "all",
        offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=100)] = 50,
    ) -> TaskListOutput:
        """List your tasks. Tag IDs identify unique tags, even with repeated names or paths."""
        token = get_access_token()
        if not token or not token.subject or "tasks:read" not in token.scopes:
            return CallToolResult(
                isError=True,
                content=[TextContent(type="text", text="Insufficient scope")],
                _meta={
                    "mcp/www_authenticate": 'Bearer error="insufficient_scope", scope="tasks:read"'
                },
            )
        if await Verifier().verify_token(token.token) is None:
            raise ValueError("Authorization no longer valid")
        with SessionLocal() as db:
            if (
                reserve_window_attempt(
                    db,
                    "mcp-user:" + token.subject,
                    datetime.now(UTC),
                    window=timedelta(minutes=1),
                    limit=120,
                )
                is None
            ):
                raise ValueError("Rate limit exceeded")
            user = db.get(User, int(token.subject))
            if not user:
                raise ValueError("Authorization no longer valid")
            return TaskListOutput(
                **query_tasks(
                    db,
                    user,
                    TaskListInput(
                        finished=finished,
                        abandoned=abandoned,
                        search=search,
                        blocked=blocked,
                        actionable=actionable,
                        include_tag_ids=include_tag_ids or [],
                        exclude_tag_ids=exclude_tag_ids or [],
                        tag_match=tag_match,
                        offset=offset,
                        limit=limit,
                    ),
                )
            )

    parsed = urlsplit(origin)
    mcp_app = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[parsed.netloc],
            allowed_origins=[origin],
        ),
    )
    return server, mcp_app
